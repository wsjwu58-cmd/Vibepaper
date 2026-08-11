"""依赖图拓扑：input 边上游遍历与执行序排序。"""

from __future__ import annotations

from collections import deque
from typing import Any


def _edge_source(e: dict) -> int:
    return int(e.get("source") or e.get("sourceNodeId") or 0)


def _edge_target(e: dict) -> int:
    return int(e.get("target") or e.get("targetNodeId") or 0)


def _edge_dep(e: dict) -> str:
    return str(e.get("dependencyType") or e.get("dependency_type") or "reference")


def _node_map(nodes: list[dict]) -> dict[int, dict]:
    return {int(n["id"]): n for n in nodes if n.get("id") is not None}


def input_edges(edges: list[dict]) -> list[dict]:
    return [e for e in edges if _edge_dep(e) == "input"]


def walk_input_upstream(edges: list[dict], nodes: list[dict], node_id: int) -> list[dict]:
    """沿 input 依赖向上游 DFS，返回从近到远的 upstream 节点摘要。"""
    nm = _node_map(nodes)
    ins = input_edges(edges)
    by_target: dict[int, list[int]] = {}
    for e in ins:
        by_target.setdefault(_edge_target(e), []).append(_edge_source(e))

    seen: set[int] = set()
    order: list[int] = []

    def dfs(nid: int):
        if nid in seen:
            return
        seen.add(nid)
        for src in by_target.get(nid, []):
            dfs(src)
            if src not in order:
                order.append(src)

    dfs(int(node_id))
    return [nm[i] for i in order if i in nm]


def topo_sort_executable(nodes: list[dict], edges: list[dict], node_ids: list[int]) -> list[int]:
    """对 node_ids 按 input 依赖拓扑排序（上游先于下游）。"""
    ids = {int(x) for x in node_ids}
    ins = [e for e in input_edges(edges) if _edge_target(e) in ids and _edge_source(e) in ids]
    indeg = {i: 0 for i in ids}
    adj: dict[int, list[int]] = {i: [] for i in ids}
    for e in ins:
        s, t = _edge_source(e), _edge_target(e)
        adj[s].append(t)
        indeg[t] = indeg.get(t, 0) + 1
    q = deque([i for i in ids if indeg.get(i, 0) == 0])
    out: list[int] = []
    while q:
        n = q.popleft()
        out.append(n)
        for nxt in adj.get(n, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    # 环或未连通：追加剩余
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def resolve_target_context(canvas_context: dict | None, target_node_id: int) -> dict[str, Any]:
    ctx = canvas_context or {}
    nodes = ctx.get("nodes") or []
    edges = ctx.get("edges") or []
    nm = _node_map(nodes)
    target = nm.get(int(target_node_id), {})
    chain = walk_input_upstream(edges, nodes, target_node_id)
    missing: list[str] = []
    ct = target.get("creativeType") or target.get("creative_type")
    ntype = target.get("type") or target.get("nodeType")
    if ct == "clip" or ntype == "video":
        ups_ct = {(u.get("creativeType") or u.get("creative_type")) for u in chain}
        if not (ups_ct & {"keyframe", "shot"}):
            missing.append("keyframe_or_shot")
    return {
        "target": target,
        "upstreamChain": chain,
        "missingInputs": missing,
        "topoOrder": [target_node_id] + [u["id"] for u in chain],
    }


def enrich_context_with_chains(canvas_context: dict, selected: list[int]) -> dict:
    """为选中节点附加 inputChains。"""
    if not selected:
        return canvas_context
    edges = canvas_context.get("edges") or []
    nodes = canvas_context.get("nodes") or []
    chains = {}
    for nid in selected:
        chains[str(nid)] = walk_input_upstream(edges, nodes, int(nid))
    out = dict(canvas_context)
    out["inputChains"] = chains
    return out


def compute_dependency_layout(
    nodes: list[dict],
    edges: list[dict],
    *,
    margin_x: int = 120,
    margin_y: int = 120,
    col_w: int = 340,
    row_h: int = 220,
    component_gap: int = 180,
) -> dict[int, tuple[int, int]]:
    """依赖图布局：让画布本身就是一张清晰的依赖图。

    规矩：
    - 单源派生放源右侧——layer = 上游最大 layer + 1，x 随层右移
    - 多输入放输入组包围盒右侧——取最右上游的下一列，纵向跟随上游重心
    - 新行（无连边的独立分量）放已有内容下方
    """
    nm = _node_map(nodes)
    ids = list(nm.keys())
    if not ids:
        return {}

    upstream: dict[int, list[int]] = {}
    for e in input_edges(edges):
        s, t = _edge_source(e), _edge_target(e)
        if s in nm and t in nm and s != t:
            upstream.setdefault(t, []).append(s)

    # 分层：input 依赖拓扑序上的最长路（成环节点按 0 层兜底）
    order = topo_sort_executable(nodes, edges, ids)
    layer: dict[int, int] = {}
    for nid in order:
        ups = [u for u in upstream.get(nid, []) if u in layer]
        layer[nid] = (max(layer[u] for u in ups) + 1) if ups else 0

    # 连通分量（所有边都算关联，含 reference）
    parent = {i: i for i in ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in edges or []:
        s, t = _edge_source(e), _edge_target(e)
        if s in nm and t in nm:
            union(s, t)

    comps: dict[int, list[int]] = {}
    for nid in ids:
        comps.setdefault(find(nid), []).append(nid)

    # 分量按当前 min(y) 排序，尽量保持用户既有阅读顺序
    def comp_key(members: list[int]) -> tuple:
        ys = [float(nm[i].get("y") or 0) for i in members]
        xs = [float(nm[i].get("x") or 0) for i in members]
        return (min(ys), min(xs))

    positions: dict[int, tuple[int, int]] = {}
    base_y = margin_y
    for members in sorted(comps.values(), key=comp_key):
        buckets: dict[int, list[int]] = {}
        for nid in members:
            buckets.setdefault(layer.get(nid, 0), []).append(nid)
        max_rows = 0
        for lv in sorted(buckets):
            bucket = buckets[lv]

            def y_key(nid: int, _ups=upstream) -> tuple:
                ups = [u for u in _ups.get(nid, []) if u in positions]
                if ups:
                    return (sum(positions[u][1] for u in ups) / len(ups), float(nm[nid].get("y") or 0))
                return (float(nm[nid].get("y") or 0), 0.0)

            bucket.sort(key=y_key)
            for idx, nid in enumerate(bucket):
                positions[nid] = (margin_x + lv * col_w, base_y + idx * row_h)
            max_rows = max(max_rows, len(bucket))
        base_y += max_rows * row_h + component_gap
    return positions
