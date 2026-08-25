"""依赖图调度：上游 ready 的节点自动 submit，按拓扑推进而非流水线干等。"""

from __future__ import annotations

from ..agent.planner import PlannedAction
from .dependency_graph import input_edges, topo_sort_executable
from .video_task import video_submit_from_node

READY_STATUSES = frozenset({"ready", "succeeded", "success"})
ACTIVE_STATUSES = frozenset({"queued", "running", "generating", "pending"})
GENERATABLE_TYPES = frozenset({"text", "image", "video", "audio"})

DEFAULT_COST = {"text": 8, "image": 8, "video": 30, "audio": 10, "compose": 15}


def _exec_status(node: dict) -> str:
    return str(node.get("execStatus") or node.get("status") or "idle").lower()


def is_node_ready(node: dict) -> bool:
    return _exec_status(node) in READY_STATUSES


def is_node_active(node: dict) -> bool:
    return _exec_status(node) in ACTIVE_STATUSES


def is_node_submittable(node: dict) -> bool:
    """idle 且为可生成类型，尚未 ready / 排队 / 已失败。

    failed 不自动重提：避免依赖唤醒反复打失败合成节点，形成死循环。
    用户点「重试」或 Agent 显式 compose_final 仍可提交。
    """
    st = _exec_status(node)
    if st in READY_STATUSES or st in ACTIVE_STATUSES or st == "failed":
        return False
    ntype = str(node.get("type") or "")
    return ntype in GENERATABLE_TYPES or ntype == "compose"


def _input_source_ids(node_id: int, edges: list[dict]) -> list[int]:
    ins = input_edges(edges)
    out: list[int] = []
    for e in ins:
        tgt = int(e.get("target") or e.get("targetNodeId") or 0)
        if tgt == int(node_id):
            src = int(e.get("source") or e.get("sourceNodeId") or 0)
            if src:
                out.append(src)
    return out


def all_inputs_ready(node_id: int, nodes: list[dict], edges: list[dict]) -> bool:
    nm = {int(n["id"]): n for n in nodes if n.get("id") is not None}
    for src_id in _input_source_ids(node_id, edges):
        src = nm.get(src_id, {})
        if not is_node_ready(src):
            return False
    return True


def find_submittable_nodes(
    canvas_context: dict | None,
    *,
    prefer_downstream_of: int | None = None,
) -> list[dict]:
    """返回当前依赖已就绪、可提交生成的节点（拓扑序）。"""
    ctx = canvas_context or {}
    nodes: list[dict] = list(ctx.get("nodes") or [])
    edges: list[dict] = list(ctx.get("edges") or [])
    if not nodes:
        return []

    candidates: list[dict] = []
    downstream_ids: set[int] | None = None
    if prefer_downstream_of is not None:
        downstream_ids = set()
        for e in input_edges(edges):
            src = int(e.get("source") or e.get("sourceNodeId") or 0)
            if src == int(prefer_downstream_of):
                downstream_ids.add(int(e.get("target") or e.get("targetNodeId") or 0))

    for n in nodes:
        nid = n.get("id")
        if nid is None or not is_node_submittable(n):
            continue
        if downstream_ids is not None and int(nid) not in downstream_ids:
            continue
        ntype = str(n.get("type") or "")
        src_ids = _input_source_ids(int(nid), edges)
        if ntype == "compose":
            if len(src_ids) >= 2 and all_inputs_ready(int(nid), nodes, edges):
                candidates.append(n)
        elif not src_ids or all_inputs_ready(int(nid), nodes, edges):
            candidates.append(n)

    if not candidates:
        return []
    ids = [int(n["id"]) for n in candidates]
    order = topo_sort_executable(nodes, edges, ids)
    nm = {int(n["id"]): n for n in nodes}
    return [nm[i] for i in order if i in nm]


def _model_type_for_node(node: dict) -> str:
    ntype = str(node.get("type") or "image")
    creative = str(node.get("creativeType") or node.get("creative_type") or "")
    if ntype == "compose":
        return "video"
    if creative in ("keyframe",):
        return "image"
    if creative in ("clip", "composite"):
        return "video"
    if creative in ("audio",):
        return "audio"
    if creative in ("script", "shot", "character"):
        return "text"
    return ntype if ntype in GENERATABLE_TYPES else "image"


def _prompt_for_submit(node: dict, canvas_context: dict | None = None) -> str:
    from .prompt_builder import refine_prompt_on_submit

    return refine_prompt_on_submit(node, canvas_context)


def plan_submit_for_node(node: dict, canvas_context: dict | None = None) -> PlannedAction | None:
    """为单个可提交节点构造 PlannedAction。"""
    if not is_node_submittable(node):
        return None
    nid = node.get("id")
    ntype = str(node.get("type") or "")
    title = (node.get("params") or {}).get("title") or ntype

    if ntype == "compose":
        prompt = _prompt_for_submit(node, canvas_context)
        return PlannedAction(
            "compose_final",
            {
                "node_id": nid,
                "estimated_cost": DEFAULT_COST["compose"],
                "model_params": {"prompt": prompt},
            },
            f"提交成片合成（{title}）",
        )

    model_type = _model_type_for_node(node)
    prompt = _prompt_for_submit(node, canvas_context)

    if model_type == "video":
        submit = video_submit_from_node(node)
        submit["node_id"] = nid
        submit.setdefault("model_params", {})["prompt"] = prompt
        return PlannedAction(
            "submit_generation",
            submit,
            f"提交视频生成（{title}）",
        )

    cost = DEFAULT_COST.get(model_type, 10)
    return PlannedAction(
        "submit_generation",
        {
            "node_id": nid,
            "model_type": model_type,
            "model_params": {"prompt": prompt, "count": 1},
            "estimated_cost": cost,
        },
        f"提交{model_type}生成（{title}）",
    )


def plan_downstream_submits(
    canvas_context: dict | None,
    completed_node_id: int | None = None,
) -> list[PlannedAction]:
    """任务完成后：找出新就绪的下游节点并规划 submit。"""
    ready_nodes = find_submittable_nodes(
        canvas_context,
        prefer_downstream_of=completed_node_id,
    )
    actions: list[PlannedAction] = []
    for n in ready_nodes:
        action = plan_submit_for_node(n, canvas_context)
        if action:
            actions.append(action)
    return actions


def estimate_downstream_cost(node_id: int, canvas_context: dict | None) -> int:
    """预估某节点全部下游（沿 input 依赖可传递）待提交节点的点数合计。

    用于「整体确认」话术：主轮次确认时告知后续自动提交的预估费用。
    与唤醒链路的实际扣费口径一致（DEFAULT_COST，点数 int）。
    """
    ctx = canvas_context or {}
    nodes: list[dict] = list(ctx.get("nodes") or [])
    edges: list[dict] = list(ctx.get("edges") or [])
    if not nodes:
        return 0
    nm = {int(n["id"]): n for n in nodes if n.get("id") is not None}
    adj: dict[int, list[int]] = {}
    for e in input_edges(edges):
        src = int(e.get("source") or e.get("sourceNodeId") or 0)
        tgt = int(e.get("target") or e.get("targetNodeId") or 0)
        if src and tgt:
            adj.setdefault(src, []).append(tgt)
    seen: set[int] = set()
    stack = [int(node_id)]
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    total = 0
    for nid in seen:
        node = nm.get(nid)
        if node and is_node_submittable(node):
            total += DEFAULT_COST.get(_model_type_for_node(node), 10)
    return total
