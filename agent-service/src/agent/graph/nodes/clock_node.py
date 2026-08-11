"""clock_node：为 exec 任务注册定时唤醒，发完即走。"""

from __future__ import annotations

from ...tools.registry import TOOLS
from ..state import AgentState

MODEL_WAIT = {
    "image": 15,
    "text": 10,
    "audio": 30,
    "video": 60,
}


def clock_node(state: AgentState) -> dict:
    events = list(state.get("events") or [])
    clock_fn = TOOLS.get("clock")
    if not clock_fn:
        return {"events": events}

    for result in state.get("executed_results") or []:
        if not (result.get("ack") and result.get("task_id")):
            continue
        model_type = result.get("model_type") or "image"
        delay = MODEL_WAIT.get(str(model_type), 30)
        note = {
            "task_id": result["task_id"],
            "node_id": result.get("node_id"),
            "session_id": state["session_id"],
            "user_id": state["user_id"],
            "canvas_id": state.get("canvas_id"),
            "model_type": result.get("model_type"),
            "workflow_auto_submit": True,
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
