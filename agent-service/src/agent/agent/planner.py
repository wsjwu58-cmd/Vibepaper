"""意图解析与行动规划。

规则引擎仅作 LLM 不可用时的工具意图 fallback；Paper Agent 三项能力依赖 LLM。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS


@dataclass
class PlannedAction:
    tool_name: str
    params: dict = field(default_factory=dict)
    summary: str = ""
    reasoning: str = ""  # 这步为什么这么做（创作者语言，展示在「推理过程」）


@dataclass
class PlanResult:
    actions: list[PlannedAction]
    reply: str = ""
    reply_type: str = "general"
    pipeline_stage: str = "text_base"
    suggestions: list[dict] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    llm_available: bool = True
    degradation_note: str = ""
    thinking: str = ""  # 整体推理：需求理解 → 方案权衡 → 模型/依赖选择理由


INTENT_RULES = [
    (re.compile(r"推进|下一阶段|advance.*pipeline|推进链路|下一层", re.I), "advance_pipeline"),
    (re.compile(r"重跑|stale|过期|重新生成.*下游|reregenerate|regenerate.*stale", re.I), "reregenerate_stale"),
    (re.compile(
        r"工作流|编排|组装.*工作流|短剧|分镜链|从零.*工作流|搭建.*链路|"
        r"总脚本.*分镜|推进.*视频层|拼接成片",
        re.I,
    ), "orchestrate_workflow"),
    (re.compile(r"梳理|总结|概括|画布.*脉络|summarize|overview", re.I), "summarize"),
    (re.compile(r"文案|slogan|标语|品牌语|copy|tagline", re.I), "copy"),
    (re.compile(r"方向|延展|脑暴|三个|brainstorm|ideas?", re.I), "directions"),
    (re.compile(r"创建|新建|增加|做一个|写一个|create|make|add.*node", re.I), "create"),
    (re.compile(r"连线|连接|串联|关联|connect|link", re.I), "connect"),
    (re.compile(r"删除|移除|去掉|清空|delete|remove|clear", re.I), "delete"),
    (re.compile(r"整理|排版|排列|布局|对齐|organize|layout|arrange", re.I), "layout"),
    (re.compile(r"修改|更新|改成|调整|设为|update|modify|change.*param", re.I), "update"),
    (re.compile(r"搜索|查找|找.*素材|找.*图片|search|find", re.I), "search"),
    (re.compile(r"模型|换.*模型|切换|switch.*model", re.I), "model"),
    (re.compile(r"生成|产出|渲染|画|做一张|做一段|generate|produce|render", re.I), "generate"),
]

PIPELINE_STAGES = ("text_base", "storyboard", "visual_anchor", "dynamic_gen", "post_production")


def classify_intent(content: str) -> str:
    for pattern, tag in INTENT_RULES:
        if pattern.search(content):
            return tag
    return "general"


def infer_query_scope(intent: str) -> str:
    """缺了才查：按意图决定上下文查询范围。"""
    if intent in ("summarize", "copy", "directions", "layout", "general", "advance_pipeline", "reregenerate_stale", "orchestrate_workflow"):
        return "summary"
    if intent in ("update", "delete", "model", "generate"):
        return "selected"
    if intent in ("create", "connect", "search"):
        return "related"
    return "summary"


def detect_pipeline_stage(canvas_context: dict | None) -> str:
    ctx = canvas_context or {}
    type_counts = ctx.get("nodeTypeCounts") or {}
    creative = ctx.get("creativeTypeCounts") or {}
    if creative.get("composite") or type_counts.get("compose"):
        return "post_production"
    if creative.get("clip") or type_counts.get("video"):
        return "dynamic_gen"
    if creative.get("keyframe") or type_counts.get("image"):
        return "visual_anchor"
    if creative.get("shot"):
        return "storyboard"
    return "text_base"


def _wants_add_to_canvas(content: str) -> bool:
    return bool(re.search(
        r"添加到画布|写入画布|创建节点|落成节点|放到画布|在画布|再画布|到画布上|画布上|创建.*画布",
        content,
    ))


def _infer_node_type(content: str) -> str:
    """产物决定节点类型：媒介词优先于主体词（「角色视频」→ video，不是 image）。"""
    if re.search(r"音频|音乐|配音|旁白|音效", content, re.I):
        return "audio"
    # 视频/短片优先——避免被「角色/形象」误判成 image
    if re.search(r"视频|短片|动画|图生视频", content, re.I):
        return "video"
    if re.search(r"图片|形象|插画|海报|角色|人物|狼|兽|铠甲|绘画|画一张|出图|镜头", content, re.I):
        return "image"
    if re.search(r"图片|图|image|illustration|poster", content, re.I):
        return "image"
    return "text"


def _plan_create_media(content: str, selected: list[int]) -> list[PlannedAction]:
    """创建媒体节点并提交生成（无选中节点时新建）。"""
    from ..domain.prompt_builder import extract_theme, prompt_for_media_create

    node_type = _infer_node_type(content)
    # 单点创建不用分镜流水线的 keyframe/clip 标签，避免 prompt 变成「镜头1/基于首帧」空壳
    prompt = prompt_for_media_create(content, node_type)
    title = extract_theme(content)[:40] or prompt[:40]
    node: dict = {
        "type": node_type,
        "x": 220,
        "y": 180,
        "params": {"prompt": prompt, "title": title},
        "prompt": prompt,
    }
    if node_type == "image":
        node["params"]["model"] = "doubao-seedream-5-0-260128"
    elif node_type == "video":
        node["params"]["model"] = "doubao-seedance-1-0-pro-250528"
    actions: list[PlannedAction] = [
        PlannedAction(
            "create_nodes", {"nodes": [node]}, f"在画布创建 {node_type} 节点",
            f"产物是{node_type}，独立成节点——可单独重跑、单独替换，不依赖其他节点",
        ),
    ]
    if node_type in ("image", "video", "audio", "text"):
        cost = {"image": 8, "video": 30, "audio": 10, "text": 8}.get(node_type, 10)
        actions.append(PlannedAction("submit_generation", {
            "node_id": (selected or [None])[0],
            "model_type": node_type,
            "model_params": {"prompt": prompt, "count": 1},
            "estimated_cost": cost,
        }, f"提交{node_type}生成任务", "无上游依赖，输入已就绪，配好即提交"))
    return actions


def _build_plan_reply(content: str, actions: list[PlannedAction]) -> str:
    """根据计划步骤生成自然语言开场白。"""
    summaries = [a.summary for a in actions if a.summary]
    if not summaries:
        return "好的，我来处理你的需求。"
    if len(summaries) == 1:
        return f"好的，{summaries[0]}。"
    joined = " → ".join(summaries[:5])
    return f"好的，我会按顺序完成：{joined}。"


def _is_text_image_pipeline(content: str) -> bool:
    """文本节点 + 图片节点 + 连线类多节点编排。"""
    has_text = bool(re.search(r"文本节点|text.*node|文案节点", content, re.I))
    has_image = bool(re.search(r"图片节点|image.*node|形象节点|插图节点", content, re.I))
    has_connect = bool(re.search(r"连接|连线|串联|关联", content))
    has_both_nodes = bool(re.search(r"文本.*图片|图片.*文本|两个节点", content))
    return (has_text and has_image) or (has_both_nodes and has_connect)


def _plan_text_image_pipeline(content: str) -> list[PlannedAction]:
    """创建文本+图片节点、连线并提交图片生成。"""
    from ..domain.prompt_builder import build_node_prompt, extract_theme

    theme = extract_theme(content)
    text_prompt = build_node_prompt(role="script", user_theme=content)
    image_prompt = build_node_prompt(role="keyframe", user_theme=content, shot_index=1, shot_count=1)
    text_node = {
        "type": "text",
        "x": 180,
        "y": 160,
        "params": {"prompt": text_prompt, "title": "文本节点"},
        "prompt": text_prompt,
        "creativeType": "script",
    }
    image_node = {
        "type": "image",
        "x": 520,
        "y": 160,
        "params": {
            "prompt": image_prompt,
            "title": theme[:40] or "图片节点",
            "model": "doubao-seedream-5-0-260128",
        },
        "prompt": image_prompt,
        "creativeType": "keyframe",
    }
    return [
        PlannedAction(
            "create_nodes", {"nodes": [text_node, image_node]}, "创建文本与图片节点",
            "文本底座与画面分成两个节点：文本供上下文，画面独立生成、独立重跑",
        ),
        PlannedAction("connect_nodes", {"edges": [{
            "sourceNodeId": "$created[0]",
            "targetNodeId": "$created[1]",
            "dependencyType": "input",
        }]}, "连接文本到图片", "文本作为图片的上游上下文；文本一改，图片自动标记过期"),
        PlannedAction("submit_generation", {
            "node_id": "$created[0]",
            "model_type": "text",
            "model_params": {"prompt": text_prompt, "count": 1},
            "estimated_cost": 8,
            "chain_estimated_cost": 8,
        }, "提交文本节点生成（上游上下文）", "只提交链路起点；图片等文本就绪后自动提交，不做无源生成"),
    ]


def _infer_next_actions(content: str, actions: list[PlannedAction], stage: str) -> list[str]:
    """根据计划推断下一步建议。"""
    hints: list[str] = []
    tools = {a.tool_name for a in actions}
    if "submit_generation" in tools:
        for a in actions:
            mt = (a.params or {}).get("model_type")
            if mt == "image":
                hints = ["图生视频", "换风格重做", "微调 Prompt 再生成"]
            elif mt == "video":
                hints = ["换运镜重做", "抽帧 / 裁剪", "接续剧情"]
            elif mt == "text":
                hints = ["生成配图", "延展三个方向", "改写文案"]
    if "create_nodes" in tools and "submit_generation" not in tools:
        hints = ["提交生成", "调整节点布局", "继续添加节点"]
    if stage in ("visual_anchor", "dynamic_gen"):
        hints = hints or ["图生视频", "添加配音", "整理画布"]
    if not hints:
        hints = ["梳理画布", "给我三个方向", "继续创作"]
    return hints[:5]


def _is_image_then_video(content: str) -> bool:
    """先出图再做视频（尚无现成图片节点，需搭 image→video 依赖链）。"""
    has_img = bool(re.search(r"图片|形象|海报|插画|出图|首帧|配图|画一张|画图", content, re.I))
    has_vid = bool(re.search(r"视频|短片|动画|镜头", content, re.I))
    if not (has_img and has_vid):
        return False
    return bool(re.search(
        r"先|再|然后|接着|之后|完成后|之后|根据|基于|用.{0,6}图",
        content,
        re.I,
    ))


def _is_image_to_video(content: str) -> bool:
    return bool(re.search(
        r"(图片|形象|海报|插画).{0,24}(视频|短片|动画)|(视频|短片).{0,24}(图片|形象)|"
        r"图生视频|合[成作]为?一?个?视频|做成视频|转成视频|生成视频",
        content,
        re.I,
    ))


def _selected_image_ready(canvas: dict | None, selected: list[int]) -> bool:
    if not selected or not canvas:
        return False
    nodes = canvas.get("nodes") or []
    nm = {int(n["id"]): n for n in nodes if n.get("id") is not None}
    node = nm.get(int(selected[0]), {})
    if str(node.get("type") or "") != "image":
        return False
    st = str(node.get("execStatus") or node.get("status") or "").lower()
    return st in ("ready", "succeeded", "success")


def _plan_image_then_video_pipeline(content: str, canvas: dict | None = None) -> list[PlannedAction]:
    """先图后视频：建 image + video、连线，仅 submit 图片；视频等上游 ready 后自动触发。"""
    from ..domain.prompt_builder import extract_theme, prompt_for_image_then_video
    from ..domain.video_task import build_video_task_params

    image_prompt, video_prompt = prompt_for_image_then_video(content)
    task = build_video_task_params(content=content, prompt=video_prompt, canvas=canvas)
    duration = task["duration"]
    model = task["model"]
    title = extract_theme(content)[:40] or "图生视频"

    image_node = {
        "type": "image",
        "x": 180,
        "y": 180,
        "params": {
            "prompt": image_prompt,
            "title": title,
            "model": "doubao-seedream-5-0-260128",
        },
        "prompt": image_prompt,
        "creativeType": "keyframe",
    }
    video_node = {
        "type": "video",
        "x": 520,
        "y": 180,
        "params": {
            "prompt": video_prompt,
            "title": f"{title}·动态",
            "model": model,
            "duration": duration,
        },
        "prompt": video_prompt,
        "creativeType": "clip",
    }
    return [
        PlannedAction(
            "create_nodes", {"nodes": [image_node, video_node]}, "创建图片与视频节点",
            "先定视觉锚点（首帧）再做动态镜头：首帧稳住画面，视频才有可靠起点",
        ),
        PlannedAction("connect_nodes", {"edges": [{
            "sourceNodeId": "$created[0]",
            "targetNodeId": "$created[1]",
            "dependencyType": "input",
        }]}, "图片 → 视频（input 依赖）", "首帧作为视频的唯一上游；首帧重出，视频跟着重跑"),
        PlannedAction("submit_generation", {
            "node_id": "$created[0]",
            "model_type": "image",
            "model_params": {"prompt": image_prompt, "count": 1},
            "estimated_cost": 8,
            "chain_estimated_cost": task["estimated_cost"],
        }, "提交图片生成（视频待输入就绪）", "只提交首帧；视频等首帧就绪后自动提交"),
    ]


def _plan_image_to_video(content: str, selected: list[int], canvas: dict | None = None) -> list[PlannedAction]:
    """已有图片节点 → 创建视频节点 → 连线；仅在上游 ready 时 submit。"""
    from ..domain.prompt_builder import extract_theme, prompt_for_image_then_video
    from ..domain.video_task import build_video_task_params

    _, video_prompt = prompt_for_image_then_video(content)
    task = build_video_task_params(
        content=content,
        prompt=video_prompt,
        canvas=canvas,
        selected_ids=selected,
    )
    duration = task["duration"]
    model = task["model"]
    actions: list[PlannedAction] = []
    if selected:
        actions.append(PlannedAction(
            "get_selected_nodes", {"node_ids": selected}, "读取选中图片节点",
            "确认选中节点的真实状态，再决定能否立即提交视频",
        ))
    actions.append(PlannedAction("create_nodes", {
        "nodes": [{
            "type": "video",
            "x": 520,
            "y": 180,
            "params": {
                "prompt": video_prompt,
                "title": extract_theme(content)[:40] or "视频片段",
                "model": model,
                "duration": duration,
            },
            "prompt": video_prompt,
            "creativeType": "clip",
        }],
    }, "创建视频生成节点", "从已有图片派生新视频节点，源图不动（源和结果分离）"))
    if selected:
        actions.append(PlannedAction("connect_nodes", {
            "edges": [{
                "sourceNodeId": selected[0],
                "targetNodeId": None,
                "dependencyType": "input",
            }],
        }, "将图片连接到视频节点", "图片作为视频的首帧上游，保持画面一致"))
    if selected and _selected_image_ready(canvas, selected):
        submit_params = dict(task)
        submit_params["model_params"] = dict(task["model_params"])
        submit_params["model_params"]["prompt"] = video_prompt
        actions.append(PlannedAction("submit_generation", {
            "node_id": None,
            "model_type": "video",
            "model_params": submit_params["model_params"],
            "estimated_cost": task["estimated_cost"],
        }, "提交视频生成（上游图片已就绪）", "上游首帧已就绪，可以立即提交；未就绪则会等唤醒后自动提交"))
    return actions


def _is_workflow_request(content: str) -> bool:
    from ..domain.workflow_orchestrator import is_workflow_orchestration_request
    return is_workflow_orchestration_request(content)


def plan(content: str, canvas: dict | None = None, selected_nodes: list[int] | None = None,
         llm: Optional[object] = None) -> list[PlannedAction]:
    """规则引擎 fallback：只规划工具意图，不生成假文案/假方向。"""
    intent = classify_intent(content)
    actions: list[PlannedAction] = []
    selected = selected_nodes or []

    if intent == "advance_pipeline":
        from ..domain.pipeline import plan_advance_pipeline
        return plan_advance_pipeline(canvas, selected).actions
    if intent == "reregenerate_stale":
        from ..domain.pipeline import plan_reregenerate_stale
        return plan_reregenerate_stale(canvas).actions
    if intent == "orchestrate_workflow":
        from ..domain.workflow_orchestrator import plan_workflow_orchestration
        return plan_workflow_orchestration(content, canvas, selected).actions

    if intent in ("summarize", "copy", "directions"):
        actions.append(PlannedAction("get_canvas_summary", {}, "读取画布摘要"))
        return actions

    if _is_image_then_video(content) and not selected:
        return _plan_image_then_video_pipeline(content, canvas)

    if _is_image_to_video(content) and selected:
        return _plan_image_to_video(content, selected, canvas)

    if _is_image_then_video(content):
        return _plan_image_then_video_pipeline(content, canvas)

    if _is_image_to_video(content):
        return _plan_image_then_video_pipeline(content, canvas)

    if _is_text_image_pipeline(content):
        return _plan_text_image_pipeline(content)

    # 创建到画布 / 生成形象图：建节点 + 提交生成
    if intent in ("create", "generate") and (
        _wants_add_to_canvas(content) or _infer_node_type(content) != "text" or intent == "generate"
    ):
        if selected and intent == "generate" and not _wants_add_to_canvas(content):
            from ..domain.prompt_builder import prompt_for_media_create

            node_type = _infer_node_type(content)
            actions.append(PlannedAction(
                "get_selected_nodes", {"node_ids": selected}, "读取选中节点",
                "先确认选中节点的真实配置与状态",
            ))
            actions.append(PlannedAction("submit_generation", {
                "node_id": selected[0],
                "model_type": node_type if node_type != "text" or "图片" in content else "text",
                "model_params": {
                    "prompt": prompt_for_media_create(content, node_type),
                    "count": 1,
                },
                "estimated_cost": 10,
            }, "提交生成任务", "基于选中节点直接生成，不新建节点"))
            return actions
        return _plan_create_media(content, selected)

    if intent == "connect":
        actions.append(PlannedAction(
            "connect_nodes", {"edges": []}, "建立节点连线",
            "用 input 依赖把上游产物喂给下游，上游一改下游自动失效",
        ))
    elif intent == "delete":
        actions.append(PlannedAction(
            "delete_nodes", {"node_ids": selected}, "删除选中节点",
            "删除不可恢复，需确认后执行",
        ))
    elif intent == "layout":
        actions.append(PlannedAction(
            "layout_nodes", {"layout": "auto"}, "一键整理画布",
            "按依赖图重排：上游在左、派生在右、独立内容放下方",
        ))
    elif intent == "update":
        from ..domain.prompt_builder import extract_theme
        # 禁止原话塞参数：剥离「把 prompt 改成」这类指令前缀，只写内容本体
        stripped = re.sub(
            r"^(把|将|帮我|请|麻烦)?.{0,12}?(的)?(prompt|提示词|参数|文案|描述|标题)?"
            r"(改成|改为|修改为|调整为|设为|设置为|更新为|换成)",
            "",
            content,
            flags=re.I,
        ).strip(" ，,：:。")
        new_prompt = stripped if stripped and stripped != content else extract_theme(content)
        actions.append(PlannedAction("update_node_config", {
            "node_id": (selected or [None])[0],
            "params": {"prompt": new_prompt[:200]},
            "changedDelta": 0,
        }, "修改节点参数", "只更新内容本体，不动其他参数；上游一改下游会标记过期"))
    elif intent == "model":
        actions.append(PlannedAction("change_model", {
            "node_id": (selected or [None])[0], "model": "deepseek-v4-pro",
        }, "切换模型", "切换模型影响生成质量与点数，需确认后执行"))
    elif intent == "search":
        actions.append(PlannedAction(
            "search_assets", {"keyword": content[:50]}, "搜索素材",
            "先从素材库找现成素材，能找到就不必重新生成",
        ))
    else:
        actions.append(PlannedAction(
            "get_canvas_summary", {}, "读取画布上下文",
            "缺少画布事实，先读摘要再决定下一步",
        ))
    return actions


def _paper_fallback_reply(intent: str, canvas_context: dict | None) -> PlanResult:
    """LLM 不可用时的明确降级，不生成低质量占位内容。"""
    stage = detect_pipeline_stage(canvas_context)
    note = "当前未配置 LLM（VIBEPAPER_LLM_API_KEY），无法生成梳理/文案/方向建议。请配置后重试。"
    return PlanResult(
        actions=[],
        reply=note,
        reply_type={"summarize": "summary", "copy": "copy", "directions": "directions"}.get(intent, "general"),
        pipeline_stage=stage,
        suggestions=[],
        next_actions=["配置 LLM API Key", "重新发送指令"],
        llm_available=False,
        degradation_note=note,
    )


def llm_plan_structured(
    content: str,
    canvas_context: dict | None,
    selected_nodes: list[int] | None,
    recent_messages: list[dict] | None,
    skill_instructions: str,
    api_key: str,
    base_url: str,
    model: str,
    long_term_prefs: list[str] | None = None,
) -> PlanResult:
    """调用 OpenAI 兼容接口做结构化规划；失败回退规则引擎。"""
    intent = classify_intent(content)
    if intent in ("advance_pipeline", "reregenerate_stale"):
        from ..domain.pipeline import plan_advance_pipeline, plan_reregenerate_stale
        if intent == "advance_pipeline":
            return plan_advance_pipeline(canvas_context, selected_nodes)
        return plan_reregenerate_stale(canvas_context)

    if intent == "orchestrate_workflow" or _is_workflow_request(content):
        from ..domain.workflow_orchestrator import plan_workflow_orchestration
        return plan_workflow_orchestration(content, canvas_context, selected_nodes)

    # 先图后视频 / 多节点编排：优先规则路径（避免 LLM 把用户原话塞进 video prompt）
    if (
        _is_image_then_video(content)
        or _is_image_to_video(content)
        or _is_text_image_pipeline(content)
        or (
            intent in ("create", "generate")
            and (_wants_add_to_canvas(content) or _infer_node_type(content) != "text")
            and not _is_image_then_video(content)
        )
    ):
        actions = plan(content, canvas_context, selected_nodes)
        stage = detect_pipeline_stage(canvas_context)
        return PlanResult(
            actions=actions,
            reply=_build_plan_reply(content, actions),
            reply_type="general",
            pipeline_stage=stage,
            next_actions=_infer_next_actions(content, actions, stage),
            requires_confirmation=False,
            llm_available=True,
        )

    if intent in ("summarize", "copy", "directions") and not api_key:
        return _paper_fallback_reply(intent, canvas_context)

    try:
        import httpx

        ctx = canvas_context or {}
        stage = detect_pipeline_stage(ctx)
        recent = recent_messages or []
        prefs = long_term_prefs or []
        system = (
            f"{AGENT_PERSONA}\n\n"
            f"{skill_instructions or PAPER_AGENT_INSTRUCTIONS}\n\n"
            "输出严格 JSON 对象（不要 Markdown）：\n"
            "{\n"
            '  "thinking": "整体推理：需求理解 → 方案权衡（若有多种拆法，说明取舍） → 模型/依赖选择理由",\n'
            '  "replyType": "summary|copy|directions|pipeline|rerun|general",\n'
            '  "reply": "见下方「回复形式」",\n'
            '  "pipelineStage": "text_base|storyboard|visual_anchor|dynamic_gen|post_production",\n'
            '  "suggestions": [{"type":"text|image","title":"","content":"","prompt":"","nodeParams":{}}],\n'
            '  "nextActions": ["..."],\n'
            '  "requiresConfirmation": false,\n'
            '  "actions": [{"tool":"...","params":{},"summary":"...","reasoning":"这步为什么这么做，1-2 句"}]\n'
            "}\n"
            "输出形式（thinking / reasoning / reply / nextActions 都会展示给用户）：\n"
            "- thinking 与 reasoning 用创作者语言（分镜/关键帧/运镜/依赖/一致性），"
            "像导演搭档在想给你看；禁止出现节点 id、工具名、内部字段名。\n"
            "- reply 固定结构：先说动作结果（一两句）→ 结论总结（涉及画布/任务时逐行列状态："
            "✅ 已完成 / ⏳ 生成中 / ⏸ 待上游就绪 / ❌ 失败及原因）→ 如有模型替换或取舍，说清理由。"
            "不要在 reply 里写下一步建议（那走 nextActions 字段，前端可点击）。\n"
            "- nextActions：2-4 条可执行建议（短句，如「推进视频层」「调整角色设定」）。\n"
            "- 先动作再理由，不寒暄；主动指出你看到的节奏/一致性风险。\n"
            "可用工具：get_canvas_summary,get_selected_nodes,list_models,search_assets,"
            "create_nodes,connect_nodes,layout_nodes,update_node_config,delete_nodes,"
            "change_model,replace_output,submit_generation,update_memory,clock,load_skill,check_task_status,"
            "upscale,compose_final,extract_frames,trim_clip。\n"
            "编排纪律：依赖图思维——先铺节点+连线，每个节点 params.prompt 必须独立撰写（禁止复制用户原话）；"
            "仅 submit 当前依赖已就绪的节点；下游由 clock 唤醒后自动 submit。"
            "长脚本先拆分镜再逐镜 Image/Video；Compose 至少 2 路视频；Upscale 基于已有素材派生。\n"
            "连线依赖：Text→Image/Video/Audio；Image→Image/Video；Video→Video/Compose；Audio→Video。\n"
            "只读建议（梳理/文案/方向）默认 actions 为空，除非用户要求添加到画布。\n"
            "用户要求创建形象/图片/角色到画布时：必须 actions 含 create_nodes(type=image) 再 submit_generation；"
            "submit_generation 的 node_id 可先留空，执行器会用刚创建的节点 ID。\n"
            "submit_generation 必须含 estimated_cost（整数点数），执行后返回 ack 而非已完成。\n"
            "视频模型默认 doubao-seedance-1-0-pro-250528（Seedance 1.0 Pro）；"
            "非用户明确要求 1.5/2.0，禁止自行改用更高版本。\n"
            f"画布摘要={json.dumps({k: ctx.get(k) for k in ('name','nodeCount','edgeCount','nodeTypeCounts','creativeTypeCounts','keywords','staleNodes','pipelineHint','inputChains','targetContext') if k in ctx}, ensure_ascii=False)}\n"
            f"选中节点={selected_nodes or []}\n"
            f"推断阶段={stage}\n"
            f"用户偏好={prefs[:5]}\n"
            f"最近对话={json.dumps(recent[-6:], ensure_ascii=False)[:1500]}"
        )
        base = (base_url or "https://api.deepseek.com/v1").rstrip("/")
        if "deepseek.com" in base and not base.endswith("/v1"):
            base = f"{base}/v1"
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
            },
            timeout=90,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"] or "{}"
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)
        actions = []
        for item in data.get("actions") or []:
            tool = item.get("tool") or item.get("tool_name")
            if not tool:
                continue
            actions.append(PlannedAction(
                tool,
                item.get("params") or {},
                item.get("summary") or tool,
                str(item.get("reasoning") or ""),
            ))
        # 只读 Paper Agent 意图：禁止静默写画布
        if intent in ("summarize", "copy", "directions") and not _wants_add_to_canvas(content):
            actions = [a for a in actions if a.tool_name.startswith(("get_", "list_", "search_", "load_"))]
        return PlanResult(
            actions=actions,
            reply=data.get("reply") or "",
            reply_type=data.get("replyType") or {
                "summarize": "summary", "copy": "copy", "directions": "directions",
            }.get(intent, "general"),
            pipeline_stage=data.get("pipelineStage") or stage,
            suggestions=data.get("suggestions") or [],
            next_actions=data.get("nextActions") or [],
            requires_confirmation=bool(data.get("requiresConfirmation")),
            llm_available=True,
            thinking=str(data.get("thinking") or ""),
        )
    except Exception as exc:
        if intent in ("summarize", "copy", "directions"):
            result = _paper_fallback_reply(intent, canvas_context)
            result.degradation_note = f"LLM 调用失败：{str(exc)[:120]}"
            result.reply = result.degradation_note + "。规则引擎无法替代创作建议。"
            return result
        actions = plan(content, canvas_context, selected_nodes)
        return PlanResult(actions=actions, reply="", reply_type="general",
                          pipeline_stage=detect_pipeline_stage(canvas_context), llm_available=False)


def llm_plan(content: str, canvas: dict | None, selected_nodes: list[int] | None, api_key: str,
             base_url: str, model: str) -> list[PlannedAction]:
    """兼容旧接口。"""
    result = llm_plan_structured(
        content, canvas, selected_nodes, None, PAPER_AGENT_INSTRUCTIONS, api_key, base_url, model,
    )
    return result.actions or plan(content, canvas, selected_nodes)
