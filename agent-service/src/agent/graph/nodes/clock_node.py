"""clock 唤醒：终态事件主路径；clock 仅兜底。"""

from __future__ import annotations

from ...core.config import settings
from ...tools.registry import TOOLS
from ..state import AgentState

MODEL_WAIT = {
    "image": 15,
    "text": 10,
    "audio": 30,
    "video": 60,
}


def clock_node(state: AgentState) -> dict:
    events: list[dict] = []
    clock_fn = TOOLS.get("clock")
    if not clock_fn:
        return {}

    fallback = max(60, int(settings.clock_fallback_delay_seconds or 600))

    for result in state.get("executed_results") or []:
        if not (result.get("ack") and result.get("task_id")):
            continue
        model_type = result.get("model_type") or "image"
        delay = fallback if settings.clock_fallback_delay_seconds else MODEL_WAIT.get(str(model_type), 30)
        note = {
            "task_id": result["task_id"],
            "node_id": result.get("node_id"),
            "session_id": state["session_id"],
            "user_id": state["user_id"],
            "canvas_id": state.get("canvas_id"),
            "model_type": result.get("model_type"),
            "workflow_auto_submit": True,
            "fallback": True,
        }
        data = clock_fn.fn(
            canvas_id=state.get("canvas_id") or 0,
            user_id=state["user_id"],
            delay=delay,
            note=note,
            callback="check_task_status",
        )
        events.append({"type": "clock_scheduled", "delay": delay, "data": data})
    return {"events": events}
