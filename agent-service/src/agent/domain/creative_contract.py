"""§3.7 创作契约硬校验：禁止非法上下游匹配（如 script 直接喂 video）。"""

from __future__ import annotations

from typing import Any

# creative_type → 允许的 input 依赖 creative_type
ALLOWED_INPUTS: dict[str, set[str]] = {
    "script": set(),
    "character": {"script"},
    "shot": {"script", "character"},
    "keyframe": {"shot", "character", "script"},
    "clip": {"keyframe", "shot", "character"},
    "audio": {"shot", "script"},
    "composite": {"clip", "audio"},
}

# node type → 生成目标允许的 upstream creative_type（submit_generation）
GENERATION_REQUIRES: dict[str, set[str]] = {
    "video": {"keyframe", "shot", "clip"},
    "image": {"keyframe", "shot", "character", "script"},
    "audio": {"shot", "script", "audio"},
    "text": {"script", "shot", "character"},
}

# creative_type → 自身可触发的 model_type
CREATIVE_TO_MODEL: dict[str, str] = {
    "keyframe": "image",
    "clip": "video",
    "audio": "audio",
    "script": "text",
    "character": "text",
    "shot": "text",
    "composite": "video",
}


def _node_map(canvas_context: dict | None) -> dict[int, dict]:
    nodes = (canvas_context or {}).get("nodes") or []
    return {int(n["id"]): n for n in nodes if n.get("id") is not None}


def _upstream_creative_types(node_id: int, canvas_context: dict | None) -> set[str]:
    edges = (canvas_context or {}).get("edges") or []
    nodes = _node_map(canvas_context)
    upstream: set[str] = set()
    for e in edges:
        dep = e.get("dependencyType") or e.get("dependency_type") or "reference"
        if dep != "input":
            continue
        target = e.get("target") or e.get("targetNodeId")
        if int(target) != int(node_id):
            continue
        source = e.get("source") or e.get("sourceNodeId")
        src = nodes.get(int(source), {})
        ct = src.get("creativeType") or src.get("creative_type")
        if ct:
            upstream.add(str(ct))
        elif src.get("type"):
            # 通用 type 映射近似
            t = str(src["type"])
            if t == "text":
                upstream.add("script")
            elif t == "image":
                upstream.add("keyframe")
            elif t == "video":
                upstream.add("clip")
    return upstream


def validate_generation(node_id: int, model_type: str, canvas_context: dict | None) -> str | None:
    """校验 submit_generation / P2 exec 是否满足创作契约。返回错误信息或 None。"""
    nodes = _node_map(canvas_context)
    node = nodes.get(int(node_id), {})
    creative = node.get("creativeType") or node.get("creative_type")
    ntype = str(node.get("type") or model_type)

    if creative == "script" and model_type in ("video", "image"):
        return "脚本节点不能直接触发生图/生视频，需先拆分为分镜/关键帧节点"

    if creative == "shot" and model_type == "video":
        upstream = _upstream_creative_types(node_id, canvas_context)
        if not (upstream & {"keyframe", "character"}):
            return "视频生成需要 keyframe/character 作为 input 依赖，当前上游不满足"

    if ntype == "video" or model_type == "video":
        upstream = _upstream_creative_types(node_id, canvas_context)
        required = GENERATION_REQUIRES.get("video", set())
        if upstream and not (upstream & required):
            return f"视频节点缺少合法上游（需要 {sorted(required)} 之一，当前 {sorted(upstream)}）"

    if creative and creative in ALLOWED_INPUTS:
        upstream = _upstream_creative_types(node_id, canvas_context)
        allowed = ALLOWED_INPUTS[creative]
        if allowed and upstream and not (upstream <= allowed | {creative}):
            bad = upstream - allowed - {creative}
            if bad:
                return f"{creative} 节点的 input 依赖不合法：{sorted(bad)}"

    return None


def validate_connect(source_id: int, target_id: int, dependency_type: str,
                     canvas_context: dict | None) -> str | None:
    if dependency_type != "input":
        return None
    nodes = _node_map(canvas_context)
    src = nodes.get(int(source_id), {})
    tgt = nodes.get(int(target_id), {})
    src_type = str(src.get("type") or "")
    tgt_type = str(tgt.get("type") or "")
    if src_type and tgt_type:
        from .workflow_orchestrator import can_feed
        if not can_feed(src_type, tgt_type):
            return f"禁止连线：{src_type} → {tgt_type}（节点类型不可喂给）"
    src_ct = src.get("creativeType") or src.get("creative_type") or (
        "script" if src.get("type") == "text" else src.get("type")
    )
    tgt_ct = tgt.get("creativeType") or tgt.get("creative_type") or (
        "script" if tgt.get("type") == "text" else tgt.get("type")
    )
    if not src_ct or not tgt_ct:
        return None
    allowed = ALLOWED_INPUTS.get(str(tgt_ct), None)
    if allowed is None:
        return None
    if str(src_ct) not in allowed and str(src_ct) != str(tgt_ct):
        return f"禁止连线：{src_ct} → {tgt_ct}（input 依赖不合法）"
    return None


def validate_action(action: dict, canvas_context: dict | None) -> str | None:
    tool = action.get("tool_name") or action.get("tool")
    params = action.get("params") or {}
    exec_tools = {
        "submit_generation", "extract_frames", "trim_clip", "upscale", "outpaint",
        "compose_final", "capture_3d_scene",
    }
    if tool in exec_tools:
        node_id = params.get("node_id") or params.get("nodeId")
        model_type = params.get("model_type") or params.get("modelType") or "image"
        if node_id is not None and str(node_id).strip().startswith("$"):
            pass  # 占位符，执行期解析
        elif node_id:
            err = validate_generation(int(node_id), str(model_type), canvas_context)
            if err:
                return err
    if tool == "connect_nodes":
        for e in params.get("edges") or []:
            dep = e.get("dependencyType") or e.get("dependency_type") or "reference"
            src = e.get("sourceNodeId") or e.get("source")
            tgt = e.get("targetNodeId") or e.get("target")
            if src is None or tgt is None:
                continue
            src_s, tgt_s = str(src).strip(), str(tgt).strip()
            if src_s.startswith("$") or tgt_s.startswith("$") or src_s in {"0", "none", "null"} or tgt_s in {"0", "none", "null"}:
                continue
            try:
                src_i, tgt_i = int(src), int(tgt)
            except (TypeError, ValueError):
                continue
            err = validate_connect(src_i, tgt_i, dep, canvas_context)
            if err:
                return err
    return None


def validate_plan(actions: list[dict], canvas_context: dict | None) -> list[dict[str, Any]]:
    """返回 [{action, error}] 校验失败项。"""
    failures = []
    for a in actions:
        err = validate_action(a, canvas_context)
        if err:
            failures.append({"action": a, "error": err})
    return failures
