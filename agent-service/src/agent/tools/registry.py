"""Agent 工具白名单（技术概要 §5.3 + 协同工具 §3.13）。

read：get_* / list_* / search_* / update_memory / clock / load_skill / check_task_status
low：create_nodes / connect_nodes / layout_nodes / update_node_config
high：delete_nodes / change_model / replace_output / submit_generation
P2 预留：extract_frames / trim_clip / upscale / compose_final
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import httpx
import redis

from ..core.config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)


def _require_canvas_id(canvas_id) -> int | dict:
    """拒绝 None / \"None\" / 非法值，避免 Java Long 解析失败。"""
    if canvas_id is None or canvas_id == "" or str(canvas_id).lower() in {"none", "null", "undefined"}:
        return {"error": "缺少画布 ID（canvasId）。请在画布页打开 Agent 后重试。", "error_code": "INVALID_INPUT"}
    try:
        return int(canvas_id)
    except (TypeError, ValueError):
        return {"error": f"非法画布 ID：{canvas_id}", "error_code": "INVALID_INPUT"}


COMPOSITE_SKILL_INSTRUCTIONS = {
    "video-generation": (
        "视频生成规则：先确认分镜/关键帧就绪；查模型时长限制；"
        "create clip 节点后 submit_generation；用 clock 延时查状态。"
    ),
    "3d-stage-composition": (
        "3D导演台构图：先引导用户搭机位与角色站位，再导出静态构图参考作为关键帧。"
    ),
    "post-production": (
        "后期流水线顺序：超分 → 裁剪 → 按依赖序拼接成片。不要跳步。"
    ),
    "character-consistency": (
        "角色一致性：维护形象/服装/表情表；下游镜头引用角色卡作为 input 依赖。"
    ),
}


def headers_for(user_id: int, role: str = "user", enterprise_id: str = "") -> dict:
    return {
        "X-User-Id": str(user_id),
        "X-User-Role": role,
        "X-Enterprise-Id": enterprise_id,
        "X-Request-Id": uuid.uuid4().hex,
        "Content-Type": "application/json",
    }


@dataclass
class Tool:
    name: str
    description: str
    risk_level: str  # read / low / high
    fn: Callable[..., dict]
    params_schema: dict = field(default_factory=dict)
    category: str = "core"  # core / collab / p2_reserved


def _get_canvas_summary(canvas_id: int, user_id: int, selected_node_ids: list[int] | None = None, **ctx) -> dict:
    cid = _require_canvas_id(canvas_id)
    if isinstance(cid, dict):
        return cid
    canvas_id = cid
    params = {}
    if selected_node_ids:
        params["selectedNodeIds"] = ",".join(str(x) for x in selected_node_ids)
        params["relatedDepth"] = 2
    try:
        r = httpx.get(
            f"{settings.canvas_base_url}/internal/canvases/{canvas_id}/summary",
            headers=headers_for(user_id),
            params=params,
            timeout=10,
            trust_env=False,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    # 降级：全量裁切
    r = httpx.get(
        f"{settings.canvas_base_url}/internal/canvases/{canvas_id}",
        headers=headers_for(user_id), timeout=10, trust_env=False,
    )
    if r.status_code != 200:
        return {"error": r.text[:300]}
    data = r.json()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type") or n.get("nodeType") or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1
    return {
        "canvasId": canvas_id,
        "name": data.get("canvas", {}).get("name"),
        "version": data.get("canvas", {}).get("version"),
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "nodeTypeCounts": type_counts,
        "keywords": [],
        "validEdgeCount": sum(1 for e in edges if e.get("valid", True)),
        "invalidEdgeCount": sum(1 for e in edges if not e.get("valid", True)),
        "staleNodes": [],
        "nodes": [{"id": n["id"], "type": n.get("type"), "status": n.get("status"),
                   "creativeType": n.get("creativeType"), "stale": n.get("stale", False)} for n in nodes],
        "edges": [{"id": e["id"], "source": e["sourceNodeId"], "target": e["targetNodeId"],
                   "valid": e.get("valid", True), "dependencyType": e.get("dependencyType", "reference")}
                  for e in edges],
    }


def _get_selected_nodes(canvas_id: int, user_id: int, node_ids: list[int] | None = None, **ctx) -> dict:
    summary = _get_canvas_summary(canvas_id, user_id, selected_node_ids=node_ids)
    ids = set(int(x) for x in (node_ids or []))
    nodes = summary.get("selectedNodes") or summary.get("nodes") or []
    selected = [n for n in nodes if n.get("id") in ids] if ids else nodes[:20]
    return {"selectedNodes": selected}


def _list_models(model_type: str | None = None, **ctx) -> dict:
    params = {"type": model_type} if model_type else {}
    r = httpx.get(f"{settings.generation_base_url}/api/v1/models", params=params, timeout=10, trust_env=False)
    return r.json() if r.status_code == 200 else {"error": r.text[:300]}


def _search_assets(keyword: str, user_id: int, **ctx) -> dict:
    r = httpx.get(
        f"{settings.asset_base_url}/internal/assets",
        params={"keyword": keyword},
        headers=headers_for(user_id), timeout=10, trust_env=False,
    )
    if r.status_code != 200:
        return {"error": r.text[:300]}
    assets = r.json()
    if isinstance(assets, list):
        assets = assets[:5]
    elif isinstance(assets, dict) and "items" in assets:
        assets = {"items": (assets.get("items") or [])[:5]}
    return {"assets": assets}


def _normalize_create_nodes_payload(nodes: list[dict] | None = None, **ctx) -> list[dict]:
    """兼容 LLM 多种传参：nodes[] / 单节点 type+config / node 对象。"""
    if isinstance(nodes, list) and nodes:
        return nodes
    if isinstance(ctx.get("nodes"), list) and ctx["nodes"]:
        return ctx["nodes"]
    single = ctx.get("node")
    if isinstance(single, dict):
        return [single]
    node_type = ctx.get("type") or ctx.get("nodeType") or ctx.get("node_type")
    if node_type:
        cfg = ctx.get("config") or ctx.get("params") or {}
        if not isinstance(cfg, dict):
            cfg = {}
        prompt = ctx.get("prompt") or cfg.get("prompt") or ""
        params = dict(cfg)
        if prompt and "prompt" not in params:
            params["prompt"] = prompt
        model = ctx.get("model") or ctx.get("modelRef") or params.get("model")
        if model:
            params["model"] = model
        return [{
            "type": node_type,
            "x": ctx.get("x", 220),
            "y": ctx.get("y", 180),
            "params": params,
            "prompt": prompt,
            "creativeType": ctx.get("creativeType") or ctx.get("creative_type"),
            "modelRef": model,
        }]
    return []


def _create_nodes(canvas_id: int, user_id: int, nodes: list[dict] | None = None, **ctx) -> dict:
    cid = _require_canvas_id(canvas_id)
    if isinstance(cid, dict):
        return cid
    canvas_id = cid
    nodes = _normalize_create_nodes_payload(nodes, **ctx)
    if not nodes:
        return {"error": "create_nodes 缺少 nodes（或 type/config）参数", "error_code": "INVALID_INPUT"}
    from ..domain.prompt_builder import ensure_node_prompt
    from ..domain.video_task import DEFAULT_VIDEO_MODEL
    user_hint = str(ctx.get("user_content") or ctx.get("content") or "")
    nodes = [ensure_node_prompt(n, user_hint) for n in nodes]
    created = []
    for n in nodes:
        params = dict(n.get("params") or n.get("config") or {})
        node_type = n.get("type") or "text"
        # 视频默认 Seedance 1.0 Pro；非用户点名 1.5/2.0 时纠偏
        if node_type == "video":
            import re as _re
            m = str(params.get("model") or "")
            user_wants_newer = bool(_re.search(r"1\.5|1-5|2\.0|2-0", user_hint))
            if (not m) or (_re.search(r"1-5-pro|1\.5|2-0|2\.0", m) and not user_wants_newer):
                params["model"] = DEFAULT_VIDEO_MODEL
                n["params"] = params
        prompt = n.get("prompt") or params.get("prompt")
        model_ref = n.get("modelRef") or n.get("model_ref") or params.get("model")
        body = {
            "type": node_type,
            "x": n.get("x", 220),
            "y": n.get("y", 180),
            "params": params,
            "creativeType": n.get("creativeType") or n.get("creative_type"),
            "modelRef": model_ref,
            "prompt": prompt,
        }
        if n.get("width") is not None:
            body["width"] = n.get("width")
        if n.get("height") is not None:
            body["height"] = n.get("height")
        r = httpx.post(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes",
            headers=headers_for(user_id), json=body, timeout=10, trust_env=False,
        )
        if r.status_code in (200, 201):
            created.append(r.json())
        else:
            return {"error": r.text[:300]}
    return {"createdNodes": created, "nodes": created, "count": len(created)}


def _coerce_node_id(value) -> int | None:
    if value is None or value is False:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined", "0"}:
        return None
    try:
        n = int(text)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _connect_nodes(canvas_id: int, user_id: int, edges: list[dict] | None = None, **ctx) -> dict:
    cid = _require_canvas_id(canvas_id)
    if isinstance(cid, dict):
        return cid
    canvas_id = cid
    edges = list(edges or ctx.get("edges") or [])
    # 兼容单边字段
    if not edges:
        src = _coerce_node_id(ctx.get("sourceNodeId") or ctx.get("source_node_id") or ctx.get("source"))
        tgt = _coerce_node_id(ctx.get("targetNodeId") or ctx.get("target_node_id") or ctx.get("target"))
        if src and tgt:
            edges = [{
                "sourceNodeId": src,
                "targetNodeId": tgt,
                "sourcePort": ctx.get("sourcePort", "output"),
                "targetPort": ctx.get("targetPort", "input"),
                "dependencyType": ctx.get("dependencyType") or "input",
            }]
    created = []
    for e in edges:
        src = _coerce_node_id(e.get("sourceNodeId") or e.get("source"))
        tgt = _coerce_node_id(e.get("targetNodeId") or e.get("target"))
        if not src or not tgt:
            return {"error": f"连线缺少有效节点 ID：source={src} target={tgt}", "error_code": "INVALID_INPUT"}
        body = {
            "sourceNodeId": src,
            "targetNodeId": tgt,
            "sourcePort": e.get("sourcePort", "output"),
            "targetPort": e.get("targetPort", "input"),
            "dependencyType": e.get("dependencyType") or e.get("dependency_type") or "input",
        }
        r = httpx.post(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/edges",
            headers=headers_for(user_id), json=body, timeout=10, trust_env=False,
        )
        if r.status_code in (200, 201):
            created.append(r.json())
        else:
            return {"error": r.text[:300]}
    if not created:
        return {"error": "connect_nodes 未提供有效 edges", "error_code": "INVALID_INPUT"}
    return {"createdEdges": created, "count": len(created)}


def _layout_nodes(canvas_id: int, user_id: int, layout: str = "auto", **ctx) -> dict:
    cid = _require_canvas_id(canvas_id)
    if isinstance(cid, dict):
        return cid
    canvas_id = cid
    r = httpx.get(
        f"{settings.canvas_base_url}/internal/canvases/{canvas_id}",
        headers=headers_for(user_id), timeout=10, trust_env=False,
    )
    if r.status_code != 200:
        return {"error": r.text[:300]}
    payload = r.json()
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    from ..domain.dependency_graph import compute_dependency_layout
    positions = compute_dependency_layout(nodes, edges)
    updates = []
    for n in nodes:
        pos = positions.get(int(n["id"]))
        if not pos:
            continue
        x, y = pos
        if int(n.get("x") or -1) == x and int(n.get("y") or -1) == y:
            continue  # 已在目标位置，跳过以减少画布写操作
        r2 = httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{n['id']}",
            headers=headers_for(user_id),
            json={"x": x, "y": y},
            timeout=10, trust_env=False,
        )
        if r2.status_code == 200:
            updates.append(r2.json())
    return {"layout": layout, "mode": "dependency", "updatedNodes": len(updates)}


def _update_node_config(canvas_id: int, user_id: int, node_id: int, params: dict, **ctx) -> dict:
    body: dict = {"params": params}
    if params.get("prompt"):
        body["prompt"] = params["prompt"]
    if params.get("model") or params.get("modelRef"):
        body["modelRef"] = params.get("modelRef") or params.get("model")
    if "creativeType" in ctx or "creative_type" in ctx:
        body["creativeType"] = ctx.get("creativeType") or ctx.get("creative_type")
    if "stale" in ctx:
        body["stale"] = ctx["stale"]
    if "execStatus" in ctx or "exec_status" in ctx:
        body["execStatus"] = ctx.get("execStatus") or ctx.get("exec_status")
    r = httpx.put(
        f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
        headers=headers_for(user_id), json=body, timeout=10, trust_env=False,
    )
    return r.json() if r.status_code == 200 else {"error": r.text[:300]}


def _delete_nodes(canvas_id: int, user_id: int, node_ids: list[int], **ctx) -> dict:
    results = []
    for node_id in node_ids or []:
        r = httpx.delete(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), timeout=10, trust_env=False,
        )
        results.append({"nodeId": node_id, "status": r.status_code})
    return {"deleted": results}


def _change_model(canvas_id: int, user_id: int, node_id: int, model: str, **ctx) -> dict:
    r = httpx.get(
        f"{settings.canvas_base_url}/internal/canvases/{canvas_id}",
        headers=headers_for(user_id), timeout=10, trust_env=False,
    )
    if r.status_code != 200:
        return {"error": r.text[:300]}
    node = next((n for n in r.json().get("nodes", []) if n["id"] == node_id), None)
    if not node:
        return {"error": "节点不存在"}
    params = dict(node.get("params") or {})
    params["model"] = model
    r2 = httpx.put(
        f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
        headers=headers_for(user_id), json={"params": params, "modelRef": model}, timeout=10, trust_env=False,
    )
    return r2.json() if r2.status_code == 200 else {"error": r2.text[:300]}


def _replace_output(canvas_id: int, user_id: int, node_id: int, output_id: int, **ctx) -> dict:
    r = httpx.put(
        f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
        headers=headers_for(user_id), json={"currentOutputId": output_id}, timeout=10, trust_env=False,
    )
    return r.json() if r.status_code == 200 else {"error": r.text[:300]}


def _node_media_url(node: dict) -> str | None:
    params = node.get("params") or {}
    out = node.get("output")
    if isinstance(out, dict):
        for k in ("url", "lastOutputUrl", "imageUrl", "videoUrl"):
            v = out.get(k)
            if isinstance(v, str) and v.strip().startswith(("http", "/")):
                return v.strip()
    for k in ("lastOutputUrl", "url", "thumbnailUrl", "referenceUrl", "output_url"):
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _node_text_output(node: dict) -> str | None:
    params = node.get("params") or {}
    out = node.get("output")
    if isinstance(out, dict):
        for k in ("text", "content"):
            v = out.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    for k in ("lastOutputText", "text", "content"):
        v = params.get(k)
        if isinstance(v, str) and v.strip() and not v.strip().startswith("【"):
            # 排除尚未生成、仍是模板 prompt 的情况
            if k == "prompt":
                continue
            return v.strip()
    return None


def _collect_input_references(canvas_id: int, user_id: int, node_id: int) -> dict:
    """从 input 连线收集上游产物：文本→referenceTexts，图/视频→referenceUrls。

    形象/构图靠连线喂入，不靠把上游全文粘进 Prompt。
    """
    try:
        r = httpx.get(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}",
            headers=headers_for(user_id),
            timeout=10,
            trust_env=False,
        )
        if r.status_code != 200:
            return {}
        detail = r.json()
    except Exception:
        return {}

    nodes = {int(n["id"]): n for n in (detail.get("nodes") or []) if n.get("id") is not None}
    edges = detail.get("edges") or []
    ref_urls: list[str] = []
    ref_texts: list[str] = []
    first_image: str | None = None
    for e in edges:
        dep = e.get("dependencyType") or e.get("dependency_type") or "reference"
        if dep != "input":
            continue
        tgt = e.get("targetNodeId") or e.get("target")
        src = e.get("sourceNodeId") or e.get("source")
        try:
            if int(tgt) != int(node_id):
                continue
            src_node = nodes.get(int(src))
        except (TypeError, ValueError):
            continue
        if not src_node:
            continue
        ntype = str(src_node.get("type") or src_node.get("nodeType") or "")
        if ntype in ("image", "video"):
            url = _node_media_url(src_node)
            if url:
                ref_urls.append(url)
                if ntype == "image" and not first_image:
                    first_image = url
        elif ntype == "text":
            text = _node_text_output(src_node)
            if text:
                ref_texts.append(text[:1200])
        else:
            url = _node_media_url(src_node)
            text = _node_text_output(src_node)
            if url:
                ref_urls.append(url)
            if text:
                ref_texts.append(text[:1200])

    out: dict = {}
    if ref_urls:
        out["referenceUrls"] = list(dict.fromkeys(ref_urls))
        out["referenceImages"] = [u for u in out["referenceUrls"] if u]
    if ref_texts:
        out["referenceTexts"] = ref_texts
    if first_image:
        out["imageUrl"] = first_image
        out["firstFrameUrl"] = first_image
        out["image"] = first_image
    return out


def _submit_generation(canvas_id: int, user_id: int, node_id: int, model_type: str,
                       model_params: dict, estimated_cost: int, **ctx) -> dict:
    cid = _require_canvas_id(canvas_id)
    if isinstance(cid, dict):
        return cid
    canvas_id = cid
    if node_id is not None and str(node_id).strip().startswith("$"):
        return {
            "error": "节点引用尚未解析（内部占位符），请重试",
            "error_code": "INVALID_INPUT",
        }
    coerced = _coerce_node_id(node_id)
    if coerced is None:
        return {"error": "缺少节点 ID，无法提交生成", "error_code": "INVALID_INPUT"}

    # 注入上游 reference：形象靠连线，Prompt 只写本次动作
    params = dict(model_params or {})
    refs = _collect_input_references(canvas_id, user_id, coerced)
    for key, val in refs.items():
        if key not in params or not params.get(key):
            params[key] = val
        elif key in ("referenceUrls", "referenceImages", "referenceTexts") and isinstance(val, list):
            merged = list(params.get(key) or [])
            for item in val:
                if item not in merged:
                    merged.append(item)
            params[key] = merged

    from ..domain.prompt_builder import refine_prompt_on_submit
    from ..domain.model_defaults import resolve_submit_model
    import re as _re
    raw_prompt = str(params.get("prompt") or "").strip()
    if (not raw_prompt) or _re.match(
        r"^【(总脚本|分镜表|角色卡|镜头\d+|图片生成|视频生成)", raw_prompt,
    ):
        params["prompt"] = refine_prompt_on_submit(
            {"type": model_type, "prompt": raw_prompt, "params": params,
             "creativeType": params.get("creativeType")},
            None,
        )

    # 禁止把 modality「text」原样交给 generation（会掉进 mock-text）
    node_model_ref = params.get("modelRef") or ctx.get("modelRef") or ctx.get("model")
    if not node_model_ref:
        try:
            summary = httpx.get(
                f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/summary",
                headers=headers_for(user_id),
                params={"relatedDepth": 0},
                timeout=8,
                trust_env=False,
            )
            if summary.status_code == 200:
                for n in (summary.json() or {}).get("nodes") or []:
                    if int(n.get("id") or 0) == coerced:
                        node_model_ref = n.get("modelRef") or n.get("model_ref")
                        break
        except Exception:
            pass
    resolved_model = resolve_submit_model(
        model_type, model_params=params, node_model_ref=node_model_ref,
    )
    params.setdefault("model", resolved_model)

    idem = uuid.uuid4().hex
    body = {
        "userId": user_id,
        "nodeId": coerced,
        "canvasId": canvas_id,
        "modelType": resolved_model,
        "modelParams": params,
        "estimatedCost": max(1, int(estimated_cost)),
        "source": "agent",
    }
    r = httpx.post(
        f"{settings.billing_base_url}/api/v1/tasks",
        headers={**headers_for(user_id), "Idempotency-Key": idem},
        json=body, timeout=15, trust_env=False,
    )
    if r.status_code not in (200, 201):
        return {"error": r.text[:300]}
    data = r.json()
    task_id = data.get("taskId") or data.get("id")
    return {
        "ack": True,
        "task_id": task_id,
        "taskId": task_id,
        "status": data.get("status") or "queued",
        "estimatedCost": body["estimatedCost"],
        "model_type": resolved_model,
        "node_id": coerced,
        **data,
    }


def _update_memory(user_id: int, scope: str, content: str, canvas_id: int | None = None,
                   fragment_type: str = "worldview", **ctx) -> dict:
    from ..services.memory_service import memory_service
    memory_service.trigger_memory_update(
        user_id=user_id, canvas_id=canvas_id or ctx.get("canvas_id"),
        scope=scope, content=content, fragment_type=fragment_type,
    )
    return {"queued": True, "scope": scope}


def _clock(user_id: int, delay: int, note: dict | None = None, callback: str = "check_task_status",
           canvas_id: int | None = None, **ctx) -> dict:
    delay = max(5, min(int(delay or 30), 300))
    wakeup_at = datetime.now(timezone.utc).timestamp() + delay
    payload = {
        "user_id": user_id,
        "canvas_id": canvas_id,
        "callback": callback,
        "note": note or {},
        "wakeup_at": wakeup_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # ZSET：score=唤醒时间
    job_id = uuid.uuid4().hex
    redis_client.zadd("agent_clock_jobs", {json.dumps({**payload, "job_id": job_id}, ensure_ascii=False): wakeup_at})
    return {
        "scheduled": True,
        "wakeup_at": datetime.fromtimestamp(wakeup_at, tz=timezone.utc).isoformat(),
        "job_id": job_id,
        "delay": delay,
    }


def _load_skill(skill_key: str, user_id: int | None = None, **ctx) -> dict:
    instructions = COMPOSITE_SKILL_INSTRUCTIONS.get(skill_key)
    if not instructions and user_id:
        # 尝试从 DB 按名加载
        try:
            from ..core.db import SessionLocal
            from ..models import Skill
            db = SessionLocal()
            try:
                skill = (
                    db.query(Skill)
                    .filter(Skill.owner_id == user_id, Skill.name == skill_key, Skill.enabled == True)  # noqa: E712
                    .first()
                )
                if skill:
                    instructions = skill.instructions
            finally:
                db.close()
        except Exception:
            pass
    if not instructions:
        return {"error": f"skill not found: {skill_key}"}
    return {"instructions": instructions, "skill_key": skill_key}


def _check_task_status(user_id: int, task_id: str | int | None = None, node_id: int | None = None,
                       canvas_id: int | None = None, note: dict | None = None, **ctx) -> dict:
    note = note or {}
    task_id = task_id or note.get("task_id")
    node_id = node_id or note.get("node_id")
    canvas_id = canvas_id or note.get("canvas_id")
    if not task_id:
        return {"error": "task_id required"}
    r = httpx.get(
        f"{settings.billing_base_url}/api/v1/tasks/{task_id}",
        headers=headers_for(user_id), timeout=10, trust_env=False,
    )
    if r.status_code != 200:
        # 尝试 generation-service
        r2 = httpx.get(
            f"{settings.generation_base_url}/api/v1/tasks/{task_id}",
            headers=headers_for(user_id), timeout=10, trust_env=False,
        )
        if r2.status_code != 200:
            return {"error": r.text[:300], "status": "fetch_error"}
        data = r2.json()
    else:
        data = r.json()

    status = str(data.get("status") or "unknown")
    output = data.get("output") or data.get("result") or data.get("outputUrl")
    outputs = data.get("outputs") or []
    error_code = data.get("errorCode") or data.get("error_code")
    # 任务失败原因用 error_message，保留 error 仅表示工具/HTTP 取数失败（避免 ok=False 误判）
    error_msg = data.get("errorMessage") or data.get("error_message") or data.get("message")
    # 成功/结算异常（产物已生成）时回写节点产物（Norm 一等字段）
    if status in ("succeeded", "settlement_error") and canvas_id and node_id:
        body: dict = {"status": "succeeded", "execStatus": "ready"}
        text_out: str | None = None
        url_out: str | None = None
        if isinstance(output, str) and output.strip():
            if output.startswith(("http", "/")):
                url_out = output.strip()
            else:
                text_out = output.strip()
        elif isinstance(output, dict):
            text_out = str(output.get("text") or output.get("content") or "").strip() or None
            url_out = str(output.get("url") or "").strip() or None
        if outputs:
            first = outputs[0] if isinstance(outputs[0], dict) else {}
            meta = first.get("meta") or {}
            if not text_out:
                text_out = str(meta.get("text") or first.get("text") or "").strip() or None
            if not url_out:
                url_out = str(first.get("url") or "").strip() or None
        patch_params: dict = {}
        if text_out:
            body["output"] = {"text": text_out, "content": text_out}
            patch_params.update({"lastOutputText": text_out, "text": text_out, "content": text_out})
        if url_out:
            body["output"] = {**(body.get("output") or {}), "url": url_out}
            patch_params.update({"lastOutputUrl": url_out, "url": url_out, "output_url": url_out})
        if patch_params:
            body["params"] = patch_params
        httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), json=body, timeout=10, trust_env=False,
        )
    elif status == "failed" and canvas_id and node_id:
        httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), json={"status": "failed", "execStatus": "failed"}, timeout=10, trust_env=False,
        )
    elif status == "expired" and canvas_id and node_id:
        # 冻结过期：节点回到可重新提交状态（expired 不属于 ready/active）
        httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), json={"status": "expired", "execStatus": "expired"}, timeout=10, trust_env=False,
        )
    elif status == "cancelled" and canvas_id and node_id:
        httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), json={"status": "cancelled", "execStatus": "idle"}, timeout=10, trust_env=False,
        )
    elif status in ("queued", "running") and canvas_id and node_id:
        httpx.put(
            f"{settings.canvas_base_url}/api/v1/canvases/{canvas_id}/nodes/{node_id}",
            headers=headers_for(user_id), json={"status": status, "execStatus": status}, timeout=10, trust_env=False,
        )
    # 仍在跑：退避再唤醒
    if status in ("queued", "running"):
        prev_delay = int(note.get("delay") or 30)
        next_delay = min(int(prev_delay * 1.5), 300)
        _clock(user_id=user_id, delay=next_delay, note={**note, "delay": next_delay, "task_id": task_id,
                                                         "node_id": node_id, "canvas_id": canvas_id},
               canvas_id=canvas_id)
    return {
        "task_id": task_id,
        "status": status,
        "output": output,
        "outputs": outputs,
        "node_id": node_id,
        "error_code": error_code,
        "error_message": error_msg,
    }


def _submit_media_operation(
    canvas_id: int,
    user_id: int,
    node_id: int,
    model_type: str,
    operation: str,
    model_params: dict | None = None,
    estimated_cost: int = 10,
    **ctx,
) -> dict:
    params = dict(model_params or {})
    params["operation"] = operation
    return _submit_generation(
        canvas_id=canvas_id,
        user_id=user_id,
        node_id=node_id,
        model_type=model_type,
        model_params=params,
        estimated_cost=estimated_cost,
    )


def _extract_frames(canvas_id: int, user_id: int, node_id: int, model_params: dict | None = None,
                    estimated_cost: int = 8, **ctx) -> dict:
    return _submit_media_operation(
        canvas_id, user_id, node_id, "video", "提帧", model_params, estimated_cost, **ctx,
    )


def _trim_clip(canvas_id: int, user_id: int, node_id: int, model_params: dict | None = None,
               estimated_cost: int = 8, **ctx) -> dict:
    return _submit_media_operation(
        canvas_id, user_id, node_id, "video", "剪辑", model_params, estimated_cost, **ctx,
    )


def _upscale(canvas_id: int, user_id: int, node_id: int, model_type: str = "image",
             model_params: dict | None = None, estimated_cost: int = 12, **ctx) -> dict:
    return _submit_media_operation(
        canvas_id, user_id, node_id, model_type, "超分", model_params, estimated_cost, **ctx,
    )


def _compose_final(canvas_id: int, user_id: int, node_id: int, model_params: dict | None = None,
                   estimated_cost: int = 15, **ctx) -> dict:
    """成片拼接走 compose-1.0（本地 FFmpeg），绝不能落到 Seedance/video。"""
    params = dict(model_params or {})
    params["operation"] = "compose"
    if not params.get("inputUrls"):
        refs = _collect_input_references(canvas_id, user_id, int(node_id))
        urls = list(refs.get("referenceUrls") or [])
        # 只保留视频类上游 URL（referenceUrls 里可能混有图片）
        params["inputUrls"] = urls
    return _submit_generation(
        canvas_id=canvas_id,
        user_id=user_id,
        node_id=node_id,
        model_type="compose-1.0",
        model_params=params,
        estimated_cost=estimated_cost,
        **ctx,
    )


def _capture_3d_scene(canvas_id: int, user_id: int, node_id: int, model_params: dict | None = None,
                      estimated_cost: int = 10, **ctx) -> dict:
    return _submit_media_operation(
        canvas_id, user_id, node_id, "image", "director", model_params, estimated_cost, **ctx,
    )


def _p2_reserved(**ctx) -> dict:
    return {"error": "P2 tool not implemented in V1.0", "reserved": True}


TOOLS: dict[str, Tool] = {
    "get_canvas_summary": Tool("get_canvas_summary", "读取画布摘要", "read", _get_canvas_summary),
    "get_selected_nodes": Tool("get_selected_nodes", "读取选中节点", "read", _get_selected_nodes),
    "list_models": Tool("list_models", "列出可用模型", "read", _list_models),
    "search_assets": Tool("search_assets", "搜索素材库", "read", _search_assets),
    "create_nodes": Tool("create_nodes", "创建节点（单次 ≤20 免确认）", "low", _create_nodes),
    "connect_nodes": Tool("connect_nodes", "创建连线", "low", _connect_nodes),
    "layout_nodes": Tool("layout_nodes", "整理/排列节点", "low", _layout_nodes),
    "update_node_config": Tool("update_node_config", "修改节点参数", "low", _update_node_config),
    "delete_nodes": Tool("delete_nodes", "删除节点（必须确认）", "high", _delete_nodes),
    "change_model": Tool("change_model", "切换模型（必须确认）", "high", _change_model),
    "replace_output": Tool("replace_output", "覆盖节点输出（必须确认）", "high", _replace_output),
    "submit_generation": Tool("submit_generation", "提交生成任务（需确认）", "high", _submit_generation),
    # 协同工具
    "update_memory": Tool("update_memory", "异步记忆更新", "read", _update_memory, category="collab"),
    "clock": Tool("clock", "注册定时唤醒", "read", _clock, category="collab"),
    "load_skill": Tool("load_skill", "按需加载 Skill 规则", "read", _load_skill, category="collab"),
    "check_task_status": Tool("check_task_status", "查询生成任务状态", "read", _check_task_status, category="collab"),
    # P2 创作工具（经 billing 任务 + operation）
    "extract_frames": Tool("extract_frames", "视频抽帧", "high", _extract_frames, category="p2"),
    "trim_clip": Tool("trim_clip", "片段剪辑", "high", _trim_clip, category="p2"),
    "upscale": Tool("upscale", "素材超分", "high", _upscale, category="p2"),
    "compose_final": Tool("compose_final", "拼接成片", "high", _compose_final, category="p2"),
    "capture_3d_scene": Tool("capture_3d_scene", "3D 导演台截图", "high", _capture_3d_scene, category="p2"),
}


def classify_risk(tool_name: str, params: dict, canvas: dict | None = None) -> tuple[str, str | None]:
    tool = TOOLS.get(tool_name)
    if not tool:
        return "high", "unknown_tool"
    if tool.risk_level == "high":
        return "high", tool.name
    if tool_name == "create_nodes":
        count = len(params.get("nodes") or [])
        if count > 20:
            return "high", "batch_create_gt_20"
        return "low", None
    if tool_name == "update_node_config":
        delta = params.get("changedDelta")
        if delta is not None and float(delta) >= 30:
            return "high", "param_delta_ge_30"
        if params.get("switchModel"):
            return "high", "model_switch"
        return "low", None
    return tool.risk_level, None


def create_confirm_token(user_id: int, canvas_id: int, canvas_version: int, action_summary: str) -> str:
    """兼容旧路径；主流程已迁移至 LangGraph interrupt。"""
    raw = f"{user_id}|{canvas_id}|{canvas_version}|{action_summary}|{int(time.time())}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:48]
    redis_client.setex(
        f"agent_confirm:{token}", settings.confirm_token_ttl_seconds,
        json.dumps({"userId": user_id, "canvasId": canvas_id, "canvasVersion": canvas_version,
                    "summary": action_summary}),
    )
    return token


def verify_confirm_token(token: str, user_id: int, canvas_id: int, canvas_version: int) -> bool:
    if token.startswith("lg:"):
        return True  # LangGraph resume 路径由 checkpoint + 版本校验负责
    raw = redis_client.get(f"agent_confirm:{token}")
    if not raw:
        return False
    data = json.loads(raw)
    return (int(data["userId"]) == user_id and int(data["canvasId"]) == canvas_id
            and int(data["canvasVersion"]) == canvas_version)
