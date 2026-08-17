"""工作流编排：按产物阶段建节点、按依赖表连线、组装可执行创作链路。

原则（产品契约）：
- 每个节点 = 一个可执行、可复用的创作意图
- Text 只做上下文前置，不偷懒「一键全生成」
- Compose 至少 2 路视频输入；Upscale 必须基于已有素材派生
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..agent.planner import PlannedAction, PlanResult, detect_pipeline_stage
from .prompt_builder import build_node_prompt, extract_theme

# 节点类型 → 可作为 input 喂给的下级类型（与 canvas EdgeRules 对齐，audio→video 已扩展）
NODE_FEED_RULES: dict[str, set[str]] = {
    "text": {"text", "image", "video", "audio"},
    "image": {"image", "video"},
    "video": {"video", "compose"},
    "audio": {"audio", "video"},
    "compose": {"video", "compose"},
    "director": {"image", "video"},
}

# creativeType → 阶段标签
STAGE_CREATES: dict[str, dict[str, Any]] = {
    "text_base": {
        "next_stage": "storyboard",
        "node": {"type": "text", "creativeType": "script", "title": "总脚本"},
        "prompt_hint": "定义故事、基调与核心叙事",
    },
    "storyboard": {
        "next_stage": "visual_anchor",
        "node": {"type": "text", "creativeType": "shot", "title": "分镜清单"},
        "connect_from_creative": ["script"],
        "prompt_hint": "拆成镜头级规格，每镜一行",
    },
    "visual_anchor": {
        "next_stage": "dynamic_gen",
        "node": {"type": "image", "creativeType": "keyframe", "title": "首帧/参考图"},
        "connect_from_creative": ["shot"],
        "prompt_hint": "确定构图与视觉定调",
    },
    "dynamic_gen": {
        "next_stage": "post_production",
        "node": {"type": "video", "creativeType": "clip", "title": "镜头视频"},
        "connect_from_creative": ["keyframe"],
        "submit": True,
        "prompt_hint": "描述运镜与动态",
    },
    "audio_layer": {
        "next_stage": "post_production",
        "node": {"type": "audio", "creativeType": "audio", "title": "旁白/配音"},
        "connect_from_creative": ["shot", "script"],
        "submit": True,
        "prompt_hint": "配音文案与语气",
    },
    "post_production": {
        "next_stage": "post_production",
        "node": {"type": "compose", "creativeType": "composite", "title": "成片"},
        "connect_from_type": ["video"],
        "min_video_inputs": 2,
        "tool": "compose_final",
    },
}


@dataclass
class WorkflowState:
    stage: str
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    script_nodes: list[dict] = field(default_factory=list)
    shot_nodes: list[dict] = field(default_factory=list)
    keyframe_nodes: list[dict] = field(default_factory=list)
    clip_nodes: list[dict] = field(default_factory=list)
    audio_nodes: list[dict] = field(default_factory=list)
    compose_nodes: list[dict] = field(default_factory=list)
    ready_clips: list[dict] = field(default_factory=list)

    @classmethod
    def from_context(cls, ctx: dict | None) -> WorkflowState:
        ctx = ctx or {}
        nodes = list(ctx.get("nodes") or [])
        edges = list(ctx.get("edges") or [])
        stage = detect_pipeline_stage(ctx)

        def by_creative(*types: str) -> list[dict]:
            return [
                n for n in nodes
                if (n.get("creativeType") or n.get("creative_type")) in types
            ]

        def ready(n: dict) -> bool:
            st = str(n.get("execStatus") or n.get("status") or "").lower()
            return st in ("ready", "succeeded", "success")

        clips = by_creative("clip")
        return cls(
            stage=stage,
            nodes=nodes,
            edges=edges,
            script_nodes=by_creative("script"),
            shot_nodes=by_creative("shot"),
            keyframe_nodes=by_creative("keyframe"),
            clip_nodes=clips,
            audio_nodes=by_creative("audio"),
            compose_nodes=[n for n in nodes if n.get("type") == "compose"],
            ready_clips=[n for n in clips if ready(n)],
        )


def can_feed(source_type: str, target_type: str) -> bool:
    return target_type in NODE_FEED_RULES.get(source_type, set())


def is_workflow_orchestration_request(content: str) -> bool:
    return bool(re.search(
        r"工作流|编排|组装|搭建.*链路|短剧|分镜链|镜头链|成片流程|"
        r"30\s*秒|广告片|逐镜头|倒推|先定产物|"
        r"总脚本.*分镜|分镜.*首帧|首帧.*视频",
        content,
        re.I,
    ))


def is_bootstrap_short_drama(content: str) -> bool:
    return bool(re.search(
        r"短剧|30\s*秒|广告|故事片|剧情|脚本.*分镜|从零|新建工作流|搭.*工作流|"
        r"搭建短剧|工作流.*生成|根据工作流|按照工作流",
        content,
        re.I,
    ))


def _pipeline_started(canvas_context: dict | None) -> bool:
    """是否已有短剧流水线（以 creativeType 为准，忽略无关散落节点）。"""
    ws = WorkflowState.from_context(canvas_context)
    return bool(ws.script_nodes or ws.shot_nodes or ws.keyframe_nodes or ws.clip_nodes)


def _wants_force_bootstrap(content: str) -> bool:
    """用户明确要求重搭时，即使已有流水线也 bootstrap（会再铺一套链路）。

    「根据/按照工作流生成」不 force：无流水线时靠 no_pipeline 进入 bootstrap；
    已有流水线时应走 advance，避免重复铺节点。
    """
    return bool(re.search(
        r"搭建短剧|搭.*工作流|新建工作流|从零|重新搭|重搭",
        content,
        re.I,
    ))


def _extract_shot_count(content: str, default: int = 3) -> int:
    m = re.search(r"(\d+)\s*[个]?镜头", content)
    if m:
        return max(1, min(int(m.group(1)), 8))
    m = re.search(r"(\d+)\s*秒", content)
    if m:
        secs = int(m.group(1))
        return max(1, min(max(1, secs // 10), 6))
    return default


def _shot_count_from_storyboard(shot_node: dict) -> int | None:
    """从分镜节点推断镜头数：prompt 中的「N 个镜头」或产物中的镜头行数。"""
    params = shot_node.get("params") or {}
    text = str(shot_node.get("prompt") or params.get("prompt") or "")
    m = re.search(r"(\d+)\s*个镜头", text)
    if m:
        return max(1, min(int(m.group(1)), 8))
    out = shot_node.get("output") or {}
    body = ""
    if isinstance(out, dict):
        body = str(out.get("text") or out.get("content") or "")
    elif isinstance(out, str):
        body = out
    if not body:
        body = str(params.get("output") or params.get("content") or "")
    if body:
        lines = [ln for ln in body.splitlines() if re.match(r"^\s*(镜头\s*)?\d+\s*[|｜、.]", ln)]
        if lines:
            return max(1, min(len(lines), 8))
    return None


def _upstream_theme(node: dict | None, max_len: int = 160) -> str:
    """取上游节点的 prompt/标题作为下游 prompt 的主题上下文。"""
    if not node:
        return ""
    params = node.get("params") or {}
    return str(node.get("prompt") or params.get("prompt") or params.get("title") or "")[:max_len]


def _node_spec(
    node_type: str,
    creative_type: str,
    title: str,
    prompt: str,
    x: int,
    y: int,
    extra_params: dict | None = None,
    *,
    task_content: str = "",
    shot_count: int | None = None,
) -> dict:
    from .video_task import resolve_video_duration, resolve_video_model_name

    params = {"prompt": prompt, "title": title, **(extra_params or {})}
    spec: dict[str, Any] = {
        "type": node_type,
        "creativeType": creative_type,
        "x": x,
        "y": y,
        "params": params,
        "prompt": prompt,
    }
    if node_type == "image":
        from .workflow_rails import IMAGE_PREF_MODEL
        params.setdefault("model", IMAGE_PREF_MODEL)
    elif node_type == "video":
        model = resolve_video_model_name(params.get("model"))
        params["model"] = model
        # 轨道参数回填（时长/比例/分辨率/音轨），不写创意正文
        from .workflow_rails import backfill_video_node_params
        params.update(backfill_video_node_params(params, user_content=task_content))
        params["model"] = model
        if "duration" not in params or params.get("duration") is None:
            params["duration"] = resolve_video_duration(
                content=task_content,
                model_name=model,
                node_params=params,
                shot_count=shot_count,
            )
    return spec


def _wants_character_card(content: str) -> bool:
    """按素材类型拆：提到主角/角色设定时独立建角色卡节点。"""
    return bool(re.search(r"主角|角色卡|角色设定|人物设定|形象设定", content))


def plan_short_drama_workflow(content: str, canvas_context: dict | None = None) -> PlanResult:
    """30 秒短剧标准链路：总脚本 → [角色卡] → 分镜 → N×(首帧→视频) → Compose。"""
    theme = extract_theme(content)
    shot_count = _extract_shot_count(content)
    with_character = _wants_character_card(content)
    actions: list[PlannedAction] = []

    actions.append(PlannedAction(
        "get_canvas_summary", {}, "读取画布现状",
        "先确认画布真实现状，避免凭空假设节点与依赖",
    ))

    script_prompt = build_node_prompt(role="script", user_theme=content)
    storyboard_prompt = build_node_prompt(role="shot", user_theme=content, shot_count=shot_count)

    script = _node_spec("text", "script", "总脚本", script_prompt, 120, 120)
    base_nodes = [script]
    # 索引：0=脚本；有角色卡时 1=角色卡、2=分镜；否则 1=分镜
    shot_idx = 2 if with_character else 1
    if with_character:
        char_prompt = build_node_prompt(role="character", user_theme=content)
        base_nodes.append(_node_spec("text", "character", "角色卡", char_prompt, 120, 200))
    storyboard = _node_spec(
        "text", "shot", "分镜清单",
        storyboard_prompt,
        120, 280 if with_character else 280,
    )
    base_nodes.append(storyboard)
    actions.append(PlannedAction(
        "create_nodes",
        {"nodes": base_nodes},
        "创建文本底座节点" + ("（含角色卡）" if with_character else ""),
        "按产物边界拆：总脚本定故事，"
        + ("角色卡锁一致性，" if with_character else "")
        + "分镜切成镜头级清单——每层独立生成、独立重跑",
    ))
    edges_base = [{
        "sourceNodeId": "$created[0]",
        "targetNodeId": f"$created[{shot_idx}]",
        "dependencyType": "input",
    }]
    if with_character:
        edges_base.extend([
            {
                "sourceNodeId": "$created[0]",
                "targetNodeId": "$created[1]",
                "dependencyType": "input",
            },
            {
                "sourceNodeId": "$created[1]",
                "targetNodeId": f"$created[{shot_idx}]",
                "dependencyType": "input",
            },
        ])
    actions.append(PlannedAction(
        "connect_nodes",
        {"edges": edges_base},
        "文本底座依赖连线",
        "分镜以总脚本为上游"
        + ("，角色卡约束外形一致性" if with_character else "")
        + "；上游一改下游自动过期",
    ))

    kf_base = shot_idx + 1  # 首帧起始 $created 下标
    image_nodes = []
    for i in range(shot_count):
        kf_prompt = build_node_prompt(
            role="keyframe", user_theme=theme, shot_index=i + 1, shot_count=shot_count,
        )
        image_nodes.append(_node_spec(
            "image", "keyframe", f"镜头{i + 1}首帧",
            kf_prompt,
            380, 80 + i * 140,
        ))
    actions.append(PlannedAction(
        "create_nodes",
        {"nodes": image_nodes},
        f"创建 {shot_count} 个首帧节点",
        "每个镜头一张独立首帧：单镜可重跑换构图，互不拖累",
    ))
    for i in range(shot_count):
        kf_edges = [{
            "sourceNodeId": f"$created[{shot_idx}]",
            "targetNodeId": f"$created[{kf_base + i}]",
            "dependencyType": "input",
        }]
        if with_character:
            kf_edges.append({
                "sourceNodeId": "$created[1]",
                "targetNodeId": f"$created[{kf_base + i}]",
                "dependencyType": "input",
            })
        actions.append(PlannedAction(
            "connect_nodes",
            {"edges": kf_edges},
            f"分镜 → 镜头{i + 1}首帧",
            "首帧参考分镜里该镜的景别与构图"
            + ("，并吃进角色卡约束" if with_character else ""),
        ))

    video_nodes = []
    base_vid = kf_base + shot_count
    from .video_task import resolve_video_duration
    clip_duration = resolve_video_duration(content=content, shot_count=shot_count)
    for i in range(shot_count):
        clip_prompt = build_node_prompt(
            role="clip",
            user_theme=theme,
            shot_index=i + 1,
            shot_count=shot_count,
            duration=clip_duration,
        )
        video_nodes.append(_node_spec(
            "video", "clip", f"镜头{i + 1}视频",
            clip_prompt,
            680, 80 + i * 140,
            task_content=content,
            shot_count=shot_count,
        ))
    actions.append(PlannedAction(
        "create_nodes",
        {"nodes": video_nodes},
        f"创建 {shot_count} 个视频节点",
        "一镜一个视频节点：运镜与节奏各自独立，单镜翻车只重跑单镜",
    ))
    for i in range(shot_count):
        actions.append(PlannedAction(
            "connect_nodes",
            {"edges": [{
                "sourceNodeId": f"$created[{kf_base + i}]",
                "targetNodeId": f"$created[{base_vid + i}]",
                "dependencyType": "input",
            }]},
            f"首帧 → 镜头{i + 1}视频",
            "首帧作为视频起点帧，锁住构图与角色形象",
        ))

    compose_prompt = build_node_prompt(role="composite", user_theme=theme, shot_count=shot_count)
    compose = _node_spec(
        "compose", "composite", "成片",
        compose_prompt,
        980, 200,
    )
    actions.append(PlannedAction(
        "create_nodes", {"nodes": [compose]}, "创建 Compose 成片节点",
        "成片节点只负责拼接，不重新生成内容；至少两路视频输入才合法",
    ))
    compose_idx = base_vid + shot_count
    compose_edges = [
        {
            "sourceNodeId": f"$created[{base_vid + i}]",
            "targetNodeId": f"$created[{compose_idx}]",
            "dependencyType": "input",
        }
        for i in range(shot_count)
    ]
    actions.append(PlannedAction(
        "connect_nodes",
        {"edges": compose_edges},
        "各镜头视频 → 成片",
        "按镜头顺序喂入各片段，任一镜重跑后成片自动标过期",
    ))
    actions.append(PlannedAction(
        "layout_nodes", {"layout": "auto"}, "按依赖图整理布局",
        "单源派生放源右侧，多输入放包围盒右侧，新行放下方——让画布本身就是依赖图",
    ))

    # 依赖图：仅 submit 无上游依赖的总脚本；其余节点等上游 ready 后由 clock 唤醒自动 submit
    # 整体确认：把整条链路的后续自动提交预估费用挂到根提交上，confirm 时一次性告知
    from .dependency_scheduler import DEFAULT_COST
    from .video_task import estimate_video_cost

    per_video_cost = DEFAULT_COST["video"]
    if video_nodes:
        first = video_nodes[0].get("params") or {}
        per_video_cost = estimate_video_cost(
            str(first.get("model") or ""), {"duration": first.get("duration"), "count": 1},
        )
    chain_estimated = (
        (DEFAULT_COST["text"] if with_character else 0)  # 角色卡
        + DEFAULT_COST["text"]  # 分镜（text）
        + DEFAULT_COST["image"] * shot_count  # 首帧
        + per_video_cost * shot_count  # 视频
        + DEFAULT_COST["compose"]  # 成片
    )
    actions.append(PlannedAction(
        "submit_generation",
        {
            "node_id": "$created[0]",
            "model_type": "text",
            "model_params": {"prompt": script_prompt, "count": 1},
            "estimated_cost": DEFAULT_COST["text"],
            "chain_estimated_cost": chain_estimated,
        },
        "提交总脚本生成（依赖链起点）",
        "只提交无上游依赖的链起点；其余节点等上游就绪后由唤醒链路自动提交，不在无源节点上浪费点数",
    ))

    stage = detect_pipeline_stage(canvas_context)
    chain_label = "总脚本 → 角色卡 → 分镜 → 首帧 → 视频 → 成片" if with_character else (
        "总脚本 → 分镜 → 首帧 → 视频 → 成片"
    )
    result = PlanResult(
        actions=actions,
        thinking=(
            f"需求是一条 {shot_count} 镜头的完整链路，不是单张图：先按产物边界拆成"
            f"总脚本、{'角色卡、' if with_character else ''}分镜，再逐镜立首帧稳住构图，"
            f"然后逐镜做动态镜头，最后拼接成片。每一环都是可独立重跑的最小单元。"
            f"主轮次只提交链起点总脚本，下游全部按依赖自动推进。"
        ),
        reply=(
            f"已按依赖图编排 {shot_count} 镜头链路：{chain_label}。"
            f"每个节点已写入独立 Prompt；总脚本已提交生成（queued 回执，不是成品），"
            f"下游节点将在依赖就绪后自动开始生成，我会持续跟进。"
            f"整条链路预估合计约 {DEFAULT_COST['text'] + chain_estimated} 点（含后续自动提交）。"
            f"若某一镜转场太硬或留白不够，告诉我，我单独重跑那一镜。"
        ),
        reply_type="pipeline",
        pipeline_stage=stage or "storyboard",
        next_actions=[],
        requires_confirmation=True,
    )
    from .methodology import audit_plan_result
    report = audit_plan_result(result, content, expect_multi_unit=True)
    if not report.ok:
        # 软失败：不阻断用户，但把审计结果挂到 thinking 便于观测
        failed = "；".join(f"P{f.principle}{f.name}" for f in report.failed())
        result.thinking = (result.thinking or "") + f"（工作方式自检告警：{failed}）"
    return result


def plan_advance_workflow_layer(canvas_context: dict | None, selected_nodes: list[int] | None = None) -> PlanResult:
    """根据当前画布状态，推进下一层可建节点（跟着产物走）。"""
    ws = WorkflowState.from_context(canvas_context)
    actions: list[PlannedAction] = []
    actions.append(PlannedAction(
        "get_canvas_summary", {}, "分析工作流阶段",
        "跟着产物走：先看画布已有什么，再决定推进哪一层",
    ))

    # 空画布 → 总脚本
    if not ws.nodes:
        script = _node_spec("text", "script", "总脚本", "在此写入故事与基调", 200, 160)
        actions.append(PlannedAction(
            "create_nodes", {"nodes": [script]}, "创建总脚本节点",
            "空画布先立文本底座：分镜、画面、视频都从脚本层长出来",
        ))
        return PlanResult(
            actions=actions,
            reply="画布为空，已创建总脚本节点。请补充主题/剧情后说「拆分分镜」。",
            reply_type="pipeline",
            pipeline_stage="text_base",
            next_actions=[],
        )

    # 有脚本无分镜 → 分镜
    if ws.script_nodes and not ws.shot_nodes:
        src = ws.script_nodes[0]
        shot = _node_spec(
            "text", "shot", "分镜清单",
            build_node_prompt(role="shot", user_theme=_upstream_theme(src), shot_count=3),
            int(src.get("x") or 200), int(src.get("y") or 160) + 160,
        )
        actions.append(PlannedAction(
            "create_nodes", {"nodes": [shot]}, "创建分镜清单节点",
            "已有脚本缺镜头级拆解：分镜把故事切成可独立生成的最小单元",
        ))
        actions.append(PlannedAction(
            "connect_nodes",
            {"edges": [{
                "sourceNodeId": src["id"],
                "targetNodeId": "$created[0]",
                "dependencyType": "input",
            }]},
            "总脚本 → 分镜",
            "分镜以脚本为上下文；脚本一改分镜自动过期",
        ))
        return PlanResult(
            actions=actions,
            reply="已创建分镜节点并连接总脚本。请完善分镜后说「生成首帧」或指定镜头数。",
            reply_type="pipeline",
            pipeline_stage="storyboard",
            next_actions=[],
        )

    # 有分镜无首帧 → 为每个 shot 或选中项创建 keyframe
    if ws.shot_nodes and not ws.keyframe_nodes:
        from .dependency_scheduler import is_node_ready

        shot = ws.shot_nodes[0]
        theme = _upstream_theme(shot)
        count = _shot_count_from_storyboard(shot) or 3
        nodes = [
            _node_spec(
                "image", "keyframe", f"镜头{i + 1}首帧",
                build_node_prompt(
                    role="keyframe", user_theme=theme, shot_index=i + 1, shot_count=count,
                ),
                400, 80 + i * 130,
            )
            for i in range(count)
        ]
        actions.append(PlannedAction(
            "create_nodes", {"nodes": nodes}, f"创建 {count} 个首帧节点",
            "分镜已就位：逐镜立首帧稳住构图，每镜独立可重跑",
        ))
        for i in range(count):
            actions.append(PlannedAction(
                "connect_nodes",
                {"edges": [{
                    "sourceNodeId": shot["id"],
                    "targetNodeId": f"$created[{i}]",
                    "dependencyType": "input",
                }]},
                f"分镜 → 镜头{i + 1}首帧",
                "首帧参考分镜中该镜的景别与构图",
            ))
        # 原则六：上游分镜未就绪则只铺节点，不盲提交
        if is_node_ready(shot):
            for i in range(count):
                actions.append(PlannedAction(
                    "submit_generation",
                    {
                        "node_id": f"$created[{i}]",
                        "model_type": "image",
                        "model_params": {"prompt": nodes[i]["prompt"], "count": 1},
                        "estimated_cost": 8,
                    },
                    f"提交镜头{i + 1}首帧生成",
                    "分镜已就绪，首帧可立即提交",
                ))
            reply = f"已为 {count} 个镜头创建首帧节点并提交生成（queued，不是成品）。"
        else:
            reply = f"已为 {count} 个镜头创建首帧节点并接好依赖；分镜尚未就绪，等上游完成后自动提交。"
        return PlanResult(
            actions=actions,
            reply=reply,
            reply_type="pipeline",
            pipeline_stage="visual_anchor",
            next_actions=[],
            requires_confirmation=is_node_ready(shot),
        )

    # 有首帧无视频 → 创建 clip 并连线
    if ws.keyframe_nodes and not ws.clip_nodes:
        from .dependency_scheduler import is_node_ready
        from .video_task import video_submit_from_node

        kfs = ws.keyframe_nodes[:6]
        storyboard_theme = _upstream_theme(ws.shot_nodes[0]) if ws.shot_nodes else ""

        def _clip_title(kf: dict, idx: int) -> str:
            m = re.search(r"镜头\s*(\d+)", str((kf.get("params") or {}).get("title") or ""))
            return f"镜头{m.group(1)}视频" if m else f"镜头{idx + 1}视频"

        nodes = [
            _node_spec(
                "video", "clip", _clip_title(n, i),
                build_node_prompt(
                    role="clip",
                    user_theme=storyboard_theme or _upstream_theme(n),
                    shot_index=i + 1,
                    shot_count=len(kfs),
                ),
                int(n.get("x") or 400) + 260, int(n.get("y") or 180),
            )
            for i, n in enumerate(kfs)
        ]
        actions.append(PlannedAction(
            "create_nodes", {"nodes": nodes}, f"创建 {len(kfs)} 个视频节点",
            "首帧齐了：逐镜做动态镜头，一镜一节点，单镜翻车只重跑单镜",
        ))
        ready_count = 0
        for i, kf in enumerate(kfs):
            actions.append(PlannedAction(
                "connect_nodes",
                {"edges": [{
                    "sourceNodeId": kf["id"],
                    "targetNodeId": f"$created[{i}]",
                    "dependencyType": "input",
                }]},
                "首帧 → 视频节点",
                "首帧作为该镜起点帧，锁住构图与角色一致性",
            ))
            # 原则六：首帧未就绪绝不提交对应视频
            if is_node_ready(kf):
                submit = video_submit_from_node(nodes[i])
                actions.append(PlannedAction(
                    "submit_generation",
                    {"node_id": f"$created[{i}]", **submit},
                    "提交视频生成（上游首帧已就绪）",
                    "该镜首帧已就绪，可以立即提交；其余镜头等唤醒后自动提交",
                ))
                ready_count += 1
        if ready_count:
            reply = f"已为 {len(kfs)} 个首帧创建视频节点；其中 {ready_count} 镜上游已就绪并已提交（queued）。"
        else:
            reply = f"已为 {len(kfs)} 个首帧创建视频节点并接好依赖；首帧尚未就绪，等上游完成后自动提交视频。"
        return PlanResult(
            actions=actions,
            reply=reply,
            reply_type="pipeline",
            pipeline_stage="dynamic_gen",
            next_actions=[],
            requires_confirmation=ready_count > 0,
        )

    # 2+ 视频 → compose
    videos = [n for n in ws.nodes if n.get("type") == "video"]
    if len(videos) >= 2 and not ws.compose_nodes:
        from .dependency_scheduler import is_node_ready

        theme = _upstream_theme(ws.script_nodes[0]) if ws.script_nodes else ""
        compose_prompt = build_node_prompt(
            role="composite", user_theme=theme or "成片合成", shot_count=len(videos[:8]),
        )
        compose = _node_spec(
            "compose", "composite", "成片",
            compose_prompt,
            900, 200,
        )
        actions.append(PlannedAction(
            "create_nodes", {"nodes": [compose]}, "创建成片节点",
            "动态镜头够了：建拼接节点出成片，只组合不重新生成内容",
        ))
        actions.append(PlannedAction(
            "connect_nodes",
            {"edges": [{
                "sourceNodeId": v["id"],
                "targetNodeId": "$created[0]",
                "dependencyType": "input",
            } for v in videos[:8]]},
            "视频片段 → 成片",
            "按镜头顺序喂入片段；任一镜重跑后成片自动标过期",
        ))
        ready_videos = [v for v in videos[:8] if is_node_ready(v)]
        if len(ready_videos) >= 2 and len(ready_videos) == len(videos[:8]):
            actions.append(PlannedAction(
                "compose_final",
                {"node_id": "$created[0]", "estimated_cost": 15, "model_params": {"prompt": compose_prompt}},
                "提交成片合成",
                "所有输入片段已就绪，合成是链路的最后一步",
            ))
            reply = f"已创建成片节点并连接 {len(videos[:8])} 路视频，提交合成（queued）。"
            needs_confirm = True
        else:
            reply = (
                f"已创建成片节点并连接 {len(videos[:8])} 路视频；"
                f"当前就绪 {len(ready_videos)} 路，等全部片段就绪后自动合成。"
            )
            needs_confirm = False
        return PlanResult(
            actions=actions,
            reply=reply,
            reply_type="pipeline",
            pipeline_stage="post_production",
            next_actions=[],
            requires_confirmation=needs_confirm,
        )

    # 已有成片 → 优先提交/重跑合成；超分需用户显式说「超分」
    if ws.compose_nodes:
        from .dependency_scheduler import DEFAULT_COST, is_node_ready

        compose = ws.compose_nodes[0]
        nid = compose.get("id")
        params = compose.get("params") or {}
        title = str(params.get("title") or "成片")
        prompt = str(compose.get("prompt") or params.get("prompt") or "").strip()
        if len(prompt) < 8:
            prompt = build_node_prompt(
                role="composite", user_theme="成片合成",
                shot_count=max(2, len(ws.clip_nodes) or 2),
            )
        if not is_node_ready(compose):
            actions.append(PlannedAction(
                "compose_final",
                {
                    "node_id": nid,
                    "estimated_cost": DEFAULT_COST.get("compose", 15),
                    "model_params": {"prompt": prompt},
                },
                f"提交「{title}」合成",
                "成片节点已在，复用上游片段提交合成，不新建链路",
            ))
            return PlanResult(
                actions=actions,
                reply=f"画布已有成片节点「{title}」，将提交合成。",
                reply_type="pipeline",
                pipeline_stage="post_production",
                next_actions=[],
                requires_confirmation=True,
            )
        return PlanResult(
            actions=[PlannedAction(
                "get_canvas_summary", {}, "成片已就绪",
                "成片已成功，汇报现状；超分需用户显式要求",
            )],
            reply=(
                f"「{title}」已就绪。"
                "若要增强画质请说「超分」；若要改某一镜请指出镜头后重跑。"
            ),
            reply_type="pipeline",
            pipeline_stage="post_production",
            next_actions=["超分成片", "重跑失败的镜头"],
        )

    # 有就绪片段但无成片节点时不应落到这里；上面已处理 2+ video。
    # 仅片段就绪的兜底：建议合成
    if ws.ready_clips and len(ws.ready_clips) >= 2:
        return PlanResult(
            actions=[PlannedAction(
                "get_canvas_summary", {}, "片段已就绪可合成",
                "视频片段够了但还没有成片节点时，应推进合成而不是超分",
            )],
            reply=f"已有 {len(ws.ready_clips)} 路就绪视频片段。请说「直接合成」提交成片。",
            reply_type="pipeline",
            pipeline_stage="post_production",
            next_actions=["直接合成"],
        )

    # 有散落节点但没有短剧流水线 —— 绝不能谎称「各层都有产物」
    if not ws.script_nodes and not ws.shot_nodes:
        return PlanResult(
            actions=[PlannedAction(
                "get_canvas_summary", {}, "检查短剧流水线",
                "画布上还没有总脚本/分镜链路，需要先搭建，而不是空转汇报",
            )],
            reply=(
                f"当前阶段：{ws.stage}。"
                f"脚本 {len(ws.script_nodes)} · 分镜 {len(ws.shot_nodes)} · "
                f"首帧 {len(ws.keyframe_nodes)} · 视频 {len(ws.clip_nodes)} · 成片 {len(ws.compose_nodes)}。"
                f"还没有短剧流水线。直接说主题（如「橘猫和恶狼短剧」）或点「搭建短剧工作流」，我来铺完整链路。"
            ),
            reply_type="pipeline",
            pipeline_stage=ws.stage,
            next_actions=[],
        )

    return PlanResult(
        actions=[PlannedAction(
            "get_canvas_summary", {}, "梳理当前工作流",
            "流水线各层已有节点，先汇报现状再请你指定下一步",
        )],
        reply=(
            f"当前阶段：{ws.stage}。"
            f"脚本 {len(ws.script_nodes)} · 分镜 {len(ws.shot_nodes)} · "
            f"首帧 {len(ws.keyframe_nodes)} · 视频 {len(ws.clip_nodes)} · 成片 {len(ws.compose_nodes)}。"
            f"可说「推进下一阶段」或指定要改的那一镜。"
        ),
        reply_type="pipeline",
        pipeline_stage=ws.stage,
        next_actions=[],
    )


def plan_workflow_orchestration(
    content: str,
    canvas_context: dict | None = None,
    selected_nodes: list[int] | None = None,
) -> PlanResult:
    """编排入口：短剧 bootstrap 或按状态推进一层。

    关键修复：不能仅凭「画布上有任意节点」就拒绝 bootstrap。
    只要短剧流水线（script/shot/…）尚未起步，或用户明确要求搭建/按工作流生成，
    就走完整链路铺设。
    """
    ctx = canvas_context or {}
    force = _wants_force_bootstrap(content)
    no_pipeline = not _pipeline_started(ctx)

    if is_bootstrap_short_drama(content) and (force or no_pipeline):
        return plan_short_drama_workflow(content, ctx)

    if re.search(r"推进|下一阶段|继续|视频层|首帧|成片|拼接", content, re.I):
        # 无流水线时「推进」也等同于先搭建
        if no_pipeline:
            return plan_short_drama_workflow(content, ctx)
        return plan_advance_workflow_layer(ctx, selected_nodes)

    if no_pipeline and is_workflow_orchestration_request(content):
        return plan_short_drama_workflow(content, ctx)

    return plan_advance_workflow_layer(ctx, selected_nodes)
