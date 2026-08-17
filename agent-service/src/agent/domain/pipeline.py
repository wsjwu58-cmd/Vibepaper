"""Paper Agent P1 专用路径：advance_pipeline / reregenerate_stale / compose_existing。"""

from __future__ import annotations

import re

from ..domain.dependency_graph import topo_sort_executable
from ..agent.planner import PlannedAction, PlanResult, detect_pipeline_stage
from .workflow_orchestrator import WorkflowState, plan_advance_workflow_layer


def wants_direct_compose(content: str) -> bool:
    """用户明确要求在已有链路上合成，而不是重建工作流。"""
    return bool(re.search(
        r"直接合成|合成成片|提交合成|拼接成片|做合成|开始合成|成片合成|"
        r"合成一下|去合成|执行合成|compose",
        content or "",
        re.I,
    ))


def wants_rebuild_workflow(content: str) -> bool:
    return bool(re.search(
        r"重新搭建|重建工作流|从零|再搭一套|新建.*链路|清空.*重来|重新创建.*工作流",
        content or "",
        re.I,
    ))


def wants_new_independent_create(content: str) -> bool:
    """用户要新建独立媒体/节点，禁止被「画布已有成片」铁路劫持成推进汇报。"""
    text = content or ""
    if re.search(r"独立|另(建|做|开|起)|单独(创建|生成|做|画)|不要走(工作流|链路)|不推进", text, re.I):
        return True
    # 明确单点创建/生成图片视频，且未要求短剧/分镜/成片推进
    if re.search(
        r"(创建|生成|画|做)(一个|一张|一条)?.{0,16}(图片|图|视频|音频|插画|海报)",
        text,
        re.I,
    ) and not re.search(r"短剧|分镜|成片|工作流|链路|推进|合成", text, re.I):
        return True
    return False


def canvas_has_workflow(canvas_context: dict | None) -> bool:
    """画布是否已有短剧/分镜链路（有则禁止默默再脚手架）。"""
    ctx = canvas_context or {}
    creative = ctx.get("creativeTypeCounts") or {}
    types = ctx.get("nodeTypeCounts") or {}
    clips = int(creative.get("clip") or types.get("video") or 0)
    compose = int(creative.get("composite") or types.get("compose") or 0)
    keyframes = int(creative.get("keyframe") or types.get("image") or 0)
    scripts = int(creative.get("script") or 0)
    shots = int(creative.get("shot") or 0)
    if clips >= 1 or compose >= 1:
        return True
    if keyframes >= 2 and (scripts or shots):
        return True
    if int(ctx.get("nodeCount") or 0) >= 6 and (scripts or shots or keyframes):
        return True
    return False


def plan_compose_existing(canvas_context: dict | None) -> PlanResult:
    """复用画布已有视频/成片节点做合成，绝不新建一套短剧脚手架。"""
    from .dependency_scheduler import DEFAULT_COST
    from .prompt_builder import build_node_prompt

    ws = WorkflowState.from_context(canvas_context)
    actions: list[PlannedAction] = [
        PlannedAction(
            "get_canvas_summary", {}, "核对已有片段与成片",
            "用户要直接合成：先确认画布真实节点，禁止再建一套链路",
        ),
    ]

    if ws.compose_nodes:
        compose = ws.compose_nodes[0]
        nid = compose.get("id")
        params = compose.get("params") or {}
        title = str(params.get("title") or compose.get("title") or "成片")
        prompt = str(compose.get("prompt") or params.get("prompt") or "").strip()
        if len(prompt) < 8:
            prompt = build_node_prompt(
                role="composite",
                user_theme="成片合成",
                shot_count=max(2, len(ws.clip_nodes) or len(ws.ready_clips) or 2),
            )
        actions.append(PlannedAction(
            "compose_final",
            {
                "node_id": nid,
                "estimated_cost": DEFAULT_COST.get("compose", 15),
                "model_params": {"prompt": prompt},
            },
            f"提交「{title}」合成",
            "复用已有成片节点与上游片段，不再创建新工作流",
        ))
        return PlanResult(
            actions=actions,
            thinking="画布已有成片节点与视频片段，按用户「直接合成」只提交 compose_final。",
            reply=f"将使用画布上已有的「{title}」节点提交合成（不新建链路）。",
            reply_type="pipeline",
            pipeline_stage="post_production",
            next_actions=[],
            requires_confirmation=True,
        )

    videos = [n for n in ws.nodes if n.get("type") == "video"]
    if len(videos) >= 2:
        # 有片段无成片：只补成片节点并合成（复用 advance 同段逻辑）
        return plan_advance_workflow_layer(canvas_context)

    return PlanResult(
        actions=actions,
        thinking="用户要求合成，但画布视频片段不足。",
        reply=(
            f"当前视频片段 {len(videos)} 个、成片节点 {len(ws.compose_nodes)} 个，"
            "还不够直接合成。请先生成至少 2 路视频片段，或说「推进下一阶段」。"
        ),
        reply_type="pipeline",
        pipeline_stage=detect_pipeline_stage(canvas_context),
        next_actions=["推进下一阶段", "重跑失败的镜头"],
    )


def plan_advance_pipeline(canvas_context: dict | None, selected_nodes: list[int] | None = None) -> PlanResult:
    """检查当前阶段并创建下一层节点 + 连线 + 可选 submit（委托工作流编排器）。"""
    return plan_advance_workflow_layer(canvas_context, selected_nodes)


def plan_reregenerate_stale(canvas_context: dict | None) -> PlanResult:
    """批量重跑 stale 下游节点（按依赖顺序 submit_generation）。

    纪律：重跑沿用节点自己的 prompt（上游变更已由画布 stale 标记表达），
    不用占位文案；对用户只说节点标题，不暴露内部节点 id。
    """
    from .dependency_scheduler import DEFAULT_COST, _model_type_for_node, _prompt_for_submit

    ctx = canvas_context or {}
    stale = ctx.get("staleNodes") or []
    if not stale:
        stale = [n for n in (ctx.get("nodes") or []) if n.get("stale")]

    if not stale:
        return PlanResult(
            actions=[PlannedAction(
                "get_canvas_summary", {}, "检查 stale 节点",
                "确认当前画布是否真有过期节点，再决定是否重跑",
            )],
            reply="当前画布没有 stale 节点需要重跑。",
            reply_type="rerun",
            pipeline_stage=detect_pipeline_stage(ctx),
            next_actions=[],
        )

    actions: list[PlannedAction] = [
        PlannedAction(
            "get_canvas_summary", {}, "读取 stale 节点列表",
            "先拿到过期节点的真实状态，再按依赖拓扑排序重跑",
        ),
    ]
    nodes = ctx.get("nodes") or []
    edges = ctx.get("edges") or []
    nodes_by_id = {int(n["id"]): n for n in nodes if n.get("id") is not None}
    stale_ids = [int(item.get("nodeId") or item.get("id")) for item in stale[:10]]
    ordered_ids = topo_sort_executable(nodes, edges, stale_ids)
    id_to_item = {int(item.get("nodeId") or item.get("id")): item for item in stale}
    titles: list[str] = []
    for node_id in ordered_ids:
        item = id_to_item.get(node_id, {})
        node = nodes_by_id.get(node_id, {})
        params = node.get("params") or {}
        title = str(params.get("title") or item.get("title") or node.get("title") or "未命名节点")
        titles.append(title)
        ntype = str(item.get("type") or node.get("type") or "image")
        prompt = str(node.get("prompt") or params.get("prompt") or "").strip()
        if len(prompt) < 20:
            prompt = _prompt_for_submit({**node, "id": node_id}, ctx)
        if ntype == "compose":
            actions.append(PlannedAction(
                "compose_final",
                {
                    "node_id": node_id,
                    "estimated_cost": DEFAULT_COST["compose"],
                    "model_params": {"prompt": prompt, "regenerate": True},
                },
                f"重跑「{title}」",
                "上游片段已变更，重新按序拼接成片（沿用原 Prompt）",
            ))
            continue
        model_type = _model_type_for_node({**node, "type": ntype})
        actions.append(PlannedAction(
            "submit_generation",
            {
                "node_id": node_id,
                "model_type": model_type,
                "model_params": {"prompt": prompt, "regenerate": True},
                "estimated_cost": DEFAULT_COST.get(model_type, 10),
            },
            f"重跑「{title}」",
            "上游已变更导致该节点过期，按依赖顺序重跑（沿用该节点原 Prompt）",
        ))

    return PlanResult(
        actions=actions,
        thinking=(
            f"检测到 {len(ordered_ids)} 个节点因上游变更被标记过期。"
            f"重跑必须沿依赖拓扑顺序，先上游后下游，且沿用各节点原 Prompt——"
            f"用户改的是上游，下游意图不该被改写。"
        ),
        reply=(
            f"将按依赖顺序重跑 {len(ordered_ids)} 个过期节点：{'、'.join(titles[:5])}"
            f"{' 等' if len(titles) > 5 else ''}（沿用各节点原 Prompt，需确认后扣费）。"
        ),
        reply_type="rerun",
        pipeline_stage=detect_pipeline_stage(ctx),
        next_actions=[],
        requires_confirmation=True,
    )
