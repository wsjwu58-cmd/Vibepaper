"""意图解析与行动规划。

规则引擎仅作 LLM 不可用时的工具意图 fallback；Paper Agent 三项能力依赖 LLM。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS
from ..domain.workflow_rails import IMAGE_PREF_MODEL, VIDEO_PREF_MODEL


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
    (re.compile(r"扩图|outpaint|扩展画面|向外扩", re.I), "outpaint"),
    (re.compile(r"超分|upscale|提升清晰|变清晰|高清化", re.I), "upscale"),
    (re.compile(r"抽帧|提帧|提取.*帧|关键帧|extract.?frame", re.I), "extract_frames"),
    (re.compile(r"剪辑|裁剪片段|截取片段|trim|剪一段", re.I), "trim_clip"),
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
    if intent in ("update", "delete", "model", "generate", "outpaint", "upscale", "extract_frames", "trim_clip"):
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


def _wants_inplace_regenerate(content: str) -> bool:
    """明确要求在原节点上重跑，而不是派生新节点。"""
    return bool(re.search(
        r"重新生成|重跑|再生成一次|在这个节点|当前节点|原节点|就地生成|覆盖生成",
        content,
    ))


def _infer_node_type(content: str) -> str:
    """产物决定节点类型：媒介词优先于主体词（「角色视频」→ video，不是 image）。"""
    if re.search(r"音频|音乐|配音|旁白|音效", content, re.I):
        return "audio"
    # 视频/短片优先——避免被「角色/形象」误判成 image；首尾帧默认出视频
    if re.search(r"视频|短片|动画|图生视频|首尾帧|首帧.?尾帧|尾帧", content, re.I):
        return "video"
    if re.search(
        r"图片|形象|插画|海报|角色|人物|狼|兽|铠甲|绘画|画一张|出图|镜头|"
        r"小狗|小猫|猫咪|狗狗|宠物|动物",
        content,
        re.I,
    ):
        return "image"
    if re.search(r"图片|图|image|illustration|poster", content, re.I):
        return "image"
    return "text"


def _plan_create_media(
    content: str,
    selected: list[int],
    canvas: dict | None = None,
) -> list[PlannedAction]:
    """创建媒体节点并提交生成；有选中参考时连线再提交新建节点。

    多选策略：
    - 文本/图/视频均可作为 input 上游（提交时注入 referenceTexts / referenceImages）
    - 目标为 video 且选中 ≥2 张图时，按顺序连前两张（首帧+尾帧候选）
    """
    from ..domain.prompt_builder import extract_theme, prompt_for_media_create

    node_type = _infer_node_type(content)
    # 选中已是图片且用户要做视频 → 走图生视频更合适，但本函数被显式调用时仍按推断类型
    prompt = prompt_for_media_create(content, node_type)
    title = extract_theme(content)[:40] or prompt[:40]

    # 根据选中节点摆放：落在选中包围盒右侧
    base_x, base_y = 220, 180
    if selected and canvas:
        nodes = {
            int(n["id"]): n
            for n in (canvas.get("selectedNodes") or canvas.get("nodes") or [])
            if n.get("id") is not None
        }
        xs, ys = [], []
        for sid in selected:
            n = nodes.get(int(sid))
            if not n:
                continue
            xs.append(float(n.get("x") or 220))
            ys.append(float(n.get("y") or 180))
        if xs:
            base_x = max(xs) + 300
            base_y = sum(ys) / len(ys)

    node: dict = {
        "type": node_type,
        "x": base_x if selected else 220,
        "y": base_y,
        "params": {"prompt": prompt, "title": title},
        "prompt": prompt,
    }
    if node_type == "image":
        node["params"]["model"] = IMAGE_PREF_MODEL
    elif node_type == "video":
        node["params"]["model"] = VIDEO_PREF_MODEL
        from ..domain.workflow_rails import backfill_video_node_params
        node["params"] = backfill_video_node_params(node["params"], user_content=content)

    actions: list[PlannedAction] = []
    if selected:
        actions.append(PlannedAction(
            "get_selected_nodes", {"node_ids": list(selected)}, "读取选中参考节点",
            "确认参考节点的提示词、参数、产物与连接，再派生下游",
        ))
    actions.append(PlannedAction(
        "create_nodes", {"nodes": [node]}, f"在画布创建 {node_type} 节点",
        (
            f"以选中节点为上游参考，新建独立 {node_type} 节点（源与结果分离）"
            if selected
            else f"产物是{node_type}，独立成节点——可单独重跑、单独替换"
        ),
    ))
    if selected:
        # video / 首尾帧：图优先按选中顺序取前 2 张，文本随后
        connect_ids = list(selected[:4])
        prefer_dual = node_type == "video" or bool(
            re.search(r"首尾帧|首帧.?尾帧", content or "", re.I)
        )
        if prefer_dual and canvas:
            nodes = {
                int(n["id"]): n
                for n in (canvas.get("selectedNodes") or canvas.get("nodes") or [])
                if n.get("id") is not None
            }
            image_ids = [
                int(sid) for sid in selected
                if str((nodes.get(int(sid)) or {}).get("type") or "") == "image"
            ]
            other_ids = [int(sid) for sid in selected if int(sid) not in image_ids]
            if len(image_ids) >= 2:
                connect_ids = image_ids[:2] + other_ids[:2]
            elif image_ids:
                connect_ids = image_ids + other_ids
        edges = [
            {
                "sourceNodeId": int(sid),
                "targetNodeId": "$created[0]",
                "dependencyType": "input",
            }
            for sid in connect_ids
        ]
        reason = "参考图/文本经 input 依赖喂给下游；提交时自动注入 reference"
        if prefer_dual and len(connect_ids) >= 2:
            reason += "；多图时按连线顺序装首帧/尾帧"
        actions.append(PlannedAction(
            "connect_nodes", {"edges": edges}, "连接选中参考 → 新节点",
            reason,
        ))
    if node_type in ("image", "video", "audio", "text"):
        cost = {"image": 8, "video": 30, "audio": 10, "text": 8}.get(node_type, 10)
        actions.append(PlannedAction("submit_generation", {
            "node_id": "$created[0]",
            "model_type": node_type,
            "model_params": {"prompt": prompt, "count": 1},
            "estimated_cost": cost,
        }, f"提交{node_type}生成任务",
           "提交新建节点；若已连参考，生成侧会自动带上上游产物"))
    return actions


def _build_plan_reply(content: str, actions: list[PlannedAction]) -> str:
    """规则路径开场：动作型，不寒暄。"""
    summaries = [a.summary for a in actions if a.summary]
    if not summaries:
        return "按你的指令开始处理。"
    if len(summaries) == 1:
        return f"{summaries[0]}。"
    joined = " → ".join(summaries[:5])
    return f"按序执行：{joined}。"


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
            "model": IMAGE_PREF_MODEL,
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
            "model": IMAGE_PREF_MODEL,
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
        # 多选图片：首帧 + 可选尾帧都连到新视频节点
        edges = [
            {
                "sourceNodeId": int(sid),
                "targetNodeId": "$created[0]",
                "dependencyType": "input",
            }
            for sid in selected[:2]
        ]
        actions.append(PlannedAction(
            "connect_nodes", {"edges": edges}, "将参考图连接到视频节点",
            "图片作为视频首帧/参考上游，保持画面一致；多图时第二张可作为尾帧候选",
        ))
    if selected and _selected_image_ready(canvas, selected):
        submit_params = dict(task)
        submit_params["model_params"] = dict(task["model_params"])
        submit_params["model_params"]["prompt"] = video_prompt
        actions.append(PlannedAction("submit_generation", {
            "node_id": "$created[0]",
            "model_type": "video",
            "model_params": submit_params["model_params"],
            "estimated_cost": task["estimated_cost"],
        }, "提交视频生成（上游图片已就绪）", "上游首帧已就绪，可以立即提交；未就绪则会等唤醒后自动提交"))
    return actions


def _plan_media_process(
    content: str,
    selected: list[int],
    tool_name: str,
    *,
    summary: str,
    reasoning: str,
    estimated_cost: int = 12,
) -> list[PlannedAction]:
    """扩图/超分/抽帧/剪辑：选中源节点后由工具内部派生新节点。"""
    if not selected:
        return [PlannedAction(
            "get_canvas_summary", {}, "读取画布并确认加工目标",
            "加工需要明确源节点，请先选中图片或视频后再说一次",
        )]
    actions: list[PlannedAction] = [
        PlannedAction(
            "get_node_detail", {"node_id": selected[0]}, "读取源节点完整信息",
            "确认源节点类型、产物与参数后再派生加工",
        ),
        PlannedAction(
            tool_name,
            {
                "node_id": selected[0],
                "estimated_cost": estimated_cost,
                "model_params": {"prompt": content[:200]},
            },
            summary,
            reasoning,
        ),
    ]
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
        # 主图走 ReAct；规则 fallback 不再搭短剧空壳
        return []

    if intent == "outpaint":
        return _plan_media_process(
            content, selected, "outpaint",
            summary="扩图（派生新图节点）",
            reasoning="从源图派生扩图结果，源图保留可回溯",
            estimated_cost=12,
        )
    if intent == "upscale":
        return _plan_media_process(
            content, selected, "upscale",
            summary="超分（派生新节点）",
            reasoning="源与结果分离：超分写到新节点，源素材不动",
            estimated_cost=12,
        )
    if intent == "extract_frames":
        return _plan_media_process(
            content, selected, "extract_frames",
            summary="抽帧（派生新图节点）",
            reasoning="从源视频派生关键帧图片，不改源视频",
            estimated_cost=8,
        )
    if intent == "trim_clip":
        return _plan_media_process(
            content, selected, "trim_clip",
            summary="剪辑（派生新视频节点）",
            reasoning="从源视频派生剪辑片段，不改源视频",
            estimated_cost=8,
        )

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
        # 默认：选中参考 → 新建下游 → 连线 → 提交；仅明确「重跑当前节点」时就地生成
        if selected and intent == "generate" and _wants_inplace_regenerate(content):
            from ..domain.prompt_builder import prompt_for_media_create

            node_type = _infer_node_type(content)
            actions.append(PlannedAction(
                "get_node_detail", {"node_id": selected[0]}, "读取选中节点完整信息",
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
            }, "提交生成任务", "在选中节点上就地重跑"))
            return actions
        return _plan_create_media(content, selected, canvas)

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
            "node_id": (selected or [None])[0], "model": "agnes-2.5-flash",
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
        next_actions=[],
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

    # 编排不再拐进短剧脚手架；交给下方 LLM 直接出 edit/exec（或规则窄路径）
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
            next_actions=[],  # 由 llm_suggest_next_actions 按上下文生成，禁止场景词表硬编码
            requires_confirmation=False,
            llm_available=True,
        )

    if intent in ("summarize", "copy", "directions") and not api_key:
        return _paper_fallback_reply(intent, canvas_context)

    try:
        import httpx

        from ..domain.llm_prompt import build_chat_messages

        ctx = canvas_context or {}
        stage = detect_pipeline_stage(ctx)
        recent = recent_messages or []
        prefs = long_term_prefs or []

        extra_rules = (
            "编排纪律：依赖图思维——先铺节点+连线，每个节点 params.prompt 必须独立撰写（禁止复制用户原话）；"
            "仅 submit 当前依赖已就绪的节点；下游由 clock 唤醒后自动 submit。"
            "长脚本先拆分镜再逐镜 Image/Video；Compose 至少 2 路视频；Upscale 基于已有素材派生。\n"
            "连线依赖：Text→Image/Video/Audio；Image→Image/Video；Video→Video/Compose；Audio→Video。\n"
            "只读建议（梳理/文案/方向）默认 actions 为空，除非用户要求添加到画布。\n"
            "用户要求创建形象/图片/角色到画布时：必须 actions 含 create_nodes(type=image) 再 submit_generation；"
            "submit_generation 的 node_id 可先留空，执行器会用刚创建的节点 ID。\n"
            "submit_generation 必须含 estimated_cost（整数点数），执行后返回 ack 而非已完成。\n"
            "视频参数（模型/时长/比例/分辨率/音轨）由工作流按偏好回填并做合法性校验；"
            "你只写画面运动描述进 prompt，不要在 actions 里编造未验证的模型名或时长上限。\n"
            "工具与 Skill 均可选调用；用户本轮指令优先级最高。"
        )
        output_contract = (
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
            "- thinking / reasoning：创作者语言（分镜/关键帧/运镜/依赖/一致性），"
            "写给用户看的判断过程；禁止节点 id、工具名、内部字段名。\n"
            "- reply 必须落在一种回复形态（临场措辞，禁止背固定模板）：\n"
            "  · 动作型——做完说结果（已建/已接/正在生成哪一镜）；\n"
            "  · 决策型——需拍板时摆选项；\n"
            "  · 建议型——节奏/转场等风险 + 可执行建议；\n"
            "  · 反对型——问题说清 + 应怎么改。\n"
            "  先动作后理由，不寒暄；工具失败写清原因与替代方案。"
            "不要在 reply 里重复 nextActions。\n"
            "- nextActions：2-4 条可点击短句，服从性格层（创作术语、简洁、有意图）；"
            "贴合当前形态与画布阶段，禁止空泛口号与固定词表。\n"
            "- 原则层：直接帮；缺了才查；讨论可建议、指令则执行；绝不把 queued 说成成品。\n"
            "- 规则层：真缺 id/状态才 read/query；否则 edit/exec；不暴露内部标识。"
        )
        messages = build_chat_messages(
            user_content=content,
            persona=AGENT_PERSONA,
            skill_instructions=skill_instructions or PAPER_AGENT_INSTRUCTIONS,
            extra_rules=extra_rules,
            output_contract=output_contract,
            include_tools=True,
            include_skills_catalog=True,
            recent_messages=recent,
            long_term_prefs=prefs,
            canvas_context=ctx,
            selected_nodes=list(selected_nodes or []),
            extra_context={"inferred_pipeline_stage": stage},
        )
        base = (base_url or "https://apihub.agnes-ai.com/v1").rstrip("/")
        if ("agnes-ai.com" in base or "deepseek.com" in base) and not base.endswith("/v1"):
            base = f"{base}/v1"
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
            },
            timeout=90,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"] or "{}"
        from ..domain.llm_json import parse_llm_json

        data = parse_llm_json(raw, expect=dict)
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


def llm_suggest_next_actions(
    *,
    content: str,
    reply: str,
    pipeline_stage: str,
    actions: list[PlannedAction],
    canvas_context: dict | None,
    api_key: str,
    base_url: str,
    model: str,
) -> list[str]:
    """规则路径未带 nextActions 时，由 LLM 按当前上下文生成 2–4 条建议。失败则返回空。"""
    if not api_key:
        return []
    try:
        import httpx

        ctx = canvas_context or {}
        action_brief = [
            {"tool": a.tool_name, "summary": a.summary}
            for a in (actions or [])[:8]
        ]
        system = (
            "你是 VibePaper 创作搭档。根据用户指令、当前回复与计划动作，"
            "输出 2–4 条可点击的下一步短句。"
            "服从性格层：镜头/分镜/节奏等创作术语；简洁有意图；跟随用户语言。"
            "短句应像建议型或动作型收尾（可执行），禁止固定词表与空泛口号，"
            "禁止节点 id / jobId / 工具名。只输出 JSON 数组，不要 Markdown。"
        )
        user = json.dumps(
            {
                "user": (content or "")[:500],
                "reply": (reply or "")[:800],
                "pipelineStage": pipeline_stage,
                "actions": action_brief,
                "canvas": {
                    k: ctx.get(k)
                    for k in (
                        "nodeCount", "nodeTypeCounts", "creativeTypeCounts",
                        "pipelineHint", "staleNodes", "keywords",
                    )
                    if k in ctx
                },
            },
            ensure_ascii=False,
        )
        base = (base_url or "https://apihub.agnes-ai.com/v1").rstrip("/")
        if ("agnes-ai.com" in base or "deepseek.com" in base) and not base.endswith("/v1"):
            base = f"{base}/v1"
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.4,
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"] or "[]"
        from ..domain.llm_json import parse_llm_json

        data = parse_llm_json(raw, expect=list)
        if not isinstance(data, list):
            return []
        out: list[str] = []
        for item in data:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
            if len(out) >= 4:
                break
        return out
    except Exception:
        return []


def llm_plan(content: str, canvas: dict | None, selected_nodes: list[int] | None, api_key: str,
             base_url: str, model: str) -> list[PlannedAction]:
    """兼容旧接口。"""
    result = llm_plan_structured(
        content, canvas, selected_nodes, None, PAPER_AGENT_INSTRUCTIONS, api_key, base_url, model,
    )
    return result.actions or plan(content, canvas, selected_nodes)
