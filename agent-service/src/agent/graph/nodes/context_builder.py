"""context_builder：按意图缺了才查，优先 summary 接口。"""

from __future__ import annotations

import json
import logging

import httpx

from ...domain.dependency_graph import enrich_context_with_chains, resolve_target_context
from ...agent.planner import classify_intent, infer_query_scope
from ...core.config import settings
from ...core.db import SessionLocal
from ...models import AgentMessage
from ...services.memory_service import memory_service
from ...tools.registry import headers_for
from ..state import AgentState

logger = logging.getLogger("agent.graph.context")


def _estimate_tokens(obj) -> int:
    return max(1, int(len(json.dumps(obj, ensure_ascii=False, default=str)) / 1.5))


def _fetch_summary(canvas_id: int, user_id: int, selected: list[int], depth: int = 2) -> dict:
    params = {}
    if selected:
        params["selectedNodeIds"] = ",".join(str(x) for x in selected)
        params["relatedDepth"] = depth
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
        logger.warning("summary API %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("summary API failed: %s", e)
    # 兼容：摘要接口不可用时降级到工具裁切
    from ...tools.registry import _get_canvas_summary
    return _get_canvas_summary(canvas_id, user_id)


def _fetch_selected_detail(canvas_id: int, user_id: int, selected: list[int]) -> dict:
    summary = _fetch_summary(canvas_id, user_id, selected, depth=1)
    nodes = summary.get("selectedNodes") or summary.get("nodes") or []
    if selected:
        ids = set(selected)
        nodes = [n for n in nodes if n.get("id") in ids]
    return {**summary, "selectedNodes": nodes, "nodes": nodes}


def context_builder_node(state: AgentState) -> dict:
    content = state["user_content"]
    intent = classify_intent(content)
    scope = infer_query_scope(intent)
    user_id = state["user_id"]
    canvas_id = state.get("canvas_id")
    selected = [int(x) for x in (state.get("selected_nodes") or [])]

    canvas_context: dict = {}
    canvas_version = state.get("canvas_version") or 1

    if canvas_id and scope != "none":
        if scope == "selected" and selected:
            canvas_context = _fetch_selected_detail(canvas_id, user_id, selected)
        else:
            canvas_context = _fetch_summary(canvas_id, user_id, selected, depth=2 if scope == "related" else 1)
        canvas_version = int(canvas_context.get("version") or canvas_version)

    if canvas_id and selected and intent in ("generate", "advance_pipeline", "update", "model"):
        canvas_context = enrich_context_with_chains(canvas_context, selected)
        if len(selected) == 1:
            canvas_context["targetContext"] = resolve_target_context(canvas_context, selected[0])
    recent: list[dict] = []
    project_memories: list[dict] = []
    long_term_prefs: list[str] = []
    db = SessionLocal()
    try:
        try:
            msgs = (
                db.query(AgentMessage)
                .filter(AgentMessage.session_id == state["session_id"])
                .order_by(AgentMessage.id.desc())
                .limit(10)
                .all()
            )
            recent = [{"role": m.role, "type": m.msg_type, "content": (m.content or "")[:400]}
                      for m in reversed(msgs)]
        except Exception as e:
            logger.warning("load recent messages failed: %s", e)
            db.rollback()
        try:
            if canvas_id:
                frags = memory_service.list_project_fragments(db, canvas_id)
                project_memories = [
                    {"type": f.fragment_type, "title": f.title, "content": f.content}
                    for f in frags[:8]
                ]
            long_term = memory_service.list_long_term(db, user_id)
            long_term_prefs = [m.content[:120] for m in long_term[:5]]
        except Exception as e:
            logger.warning("load memories failed: %s", e)
            db.rollback()
    finally:
        db.close()

    token_est = _estimate_tokens(canvas_context) + _estimate_tokens(recent)
    events = list(state.get("events") or [])
    events.append({
        "type": "context",
        "canvasSummary": {
            "nodeCount": canvas_context.get("nodeCount", 0),
            "edgeCount": canvas_context.get("edgeCount", 0),
            "queryScope": scope,
            "intentType": intent,
            "tokenEstimate": token_est,
        },
    })
    logger.info(
        "context_builder session=%s intent=%s scope=%s tokens≈%s nodes=%s",
        state["session_id"], intent, scope, token_est, canvas_context.get("nodeCount"),
    )
    return {
        "intent_type": intent,
        "query_scope": scope,
        "canvas_context": canvas_context,
        "canvas_version": canvas_version,
        "recent_messages": recent,
        "project_memories": project_memories,
        "long_term_prefs": long_term_prefs,
        "context_token_estimate": token_est,
        "events": events,
    }
