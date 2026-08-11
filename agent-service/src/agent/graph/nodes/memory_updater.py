"""memory_updater：三关判据后 LangGraph 记忆子图 + Celery 降级。"""

from __future__ import annotations

from ...services.memory_service import memory_service
from ...tools.registry import TOOLS
from ..memory_subgraph import run_memory_subgraph
from ..state import AgentState


def memory_updater_node(state: AgentState) -> dict:
    events = list(state.get("events") or [])
    state_view = {
        "user_id": state["user_id"],
        "canvas_id": state.get("canvas_id"),
        "canvas_context": state.get("canvas_context") or {},
    }
    for result in state.get("executed_results") or []:
        if not memory_service.should_remember(result, state_view):
            continue
        scope = memory_service.classify_scope(result, state_view)
        if not scope:
            continue
        content = str((result.get("data") or result.get("summary") or result.get("tool")))[:500]
        task = {
            "user_id": state["user_id"],
            "canvas_id": state.get("canvas_id"),
            "scope": scope,
            "content": content,
            "fragment_type": "style" if scope == "project" else "preference",
        }
        try:
            subgraph_result = run_memory_subgraph(task)
            events.append({"type": "memory_processed", "scope": scope, "data": subgraph_result})
        except Exception:
            if "update_memory" in TOOLS:
                ack = TOOLS["update_memory"].fn(
                    canvas_id=state.get("canvas_id") or 0,
                    user_id=state["user_id"],
                    scope=scope,
                    content=content,
                    fragment_type=task["fragment_type"],
                )
                events.append({"type": "memory_queued", "scope": scope, "data": ack})
            else:
                memory_service.trigger_memory_update(
                    user_id=state["user_id"],
                    canvas_id=state.get("canvas_id"),
                    scope=scope,
                    content=content,
                )
                events.append({"type": "memory_queued", "scope": scope, "data": {"queued": True}})
    return {"events": events}
