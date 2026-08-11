"""Paper Agent P1 专用路径：advance_pipeline / reregenerate_stale。"""

from __future__ import annotations

from ..domain.dependency_graph import topo_sort_executable
from ..agent.planner import PlannedAction, PlanResult, detect_pipeline_stage
from .workflow_orchestrator import plan_advance_workflow_layer


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
            next_actions=["修改上游节点后会自动标记 stale"],
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
        next_actions=[f"重跑「{t}」" for t in titles[:5]],
        requires_confirmation=True,
    )
