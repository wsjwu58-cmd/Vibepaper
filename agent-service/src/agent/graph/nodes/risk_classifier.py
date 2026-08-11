"""risk_classifier：对动作分级，分离可执行与待确认；§3.7 契约硬校验。"""

from __future__ import annotations

import time
import itertools

from ...domain.creative_contract import validate_action
from ...tools.registry import classify_risk
from ..state import AgentState, PlannedActionDict

_id_seq = itertools.count(1)


def _next_id() -> int:
    return (int(time.time() * 1000) << 20) | (next(_id_seq) & 0xFFFFF)


def risk_classifier_node(state: AgentState) -> dict:
    canvas = state.get("canvas_context")
    pending_high: list[PlannedActionDict] = []
    executable: list[PlannedActionDict] = []
    contract_violations: list[dict] = []
    events = list(state.get("events") or [])

    for action in state.get("planned_actions") or []:
        err = validate_action(action, canvas)
        if err:
            contract_violations.append({"action": action, "error": err})
            events.append({
                "type": "contract_violation",
                "tool": action.get("tool_name"),
                "error": err,
            })
            blocked: PlannedActionDict = {
                **action,
                "risk_level": "high",
                "confirm_reason": "contract_violation",
                "action_id": action.get("action_id") or _next_id(),
                "status": "blocked",
            }
            pending_high.append(blocked)
            continue

        risk, reason = classify_risk(action["tool_name"], action.get("params") or {}, canvas)
        enriched: PlannedActionDict = {
            **action,
            "risk_level": risk,
            "confirm_reason": reason,
            "action_id": action.get("action_id") or _next_id(),
            "status": "awaiting_confirm" if risk == "high" else "ready",
        }
        if risk == "high":
            pending_high.append(enriched)
        else:
            executable.append(enriched)

    return {
        "pending_high_risk": pending_high,
        "executable_actions": executable,
        "planned_actions": executable + pending_high,
        "contract_violations": contract_violations,
        "events": events,
    }
