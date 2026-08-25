"""单工具 worker：供 LangGraph Send() 并行调度只读工具。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ...core.db import SessionLocal
from ...models import AgentAction
from ...services.telemetry import agent_action_fail, agent_action_success
from ...tools.registry import TOOLS
from ..state import AgentState, PlannedActionDict
from .executor import _call_tool, _write_result_message
from .risk_classifier import _next_id

logger = logging.getLogger("agent.graph.tool_worker")


def tool_worker_node(state: AgentState) -> dict:
    """执行 state['current_action'] 单条动作，结果追加到 executed_results。"""
    action: PlannedActionDict = state.get("current_action") or {}
    if not action:
        return {}

    tool_name = action["tool_name"]
    params = dict(action.get("params") or {})
    action_id = int(action.get("action_id") or _next_id())
    user_id = state["user_id"]
    canvas_id = state.get("canvas_id")
    canvas_version = int(state.get("canvas_version") or 1)

    # operator.add：只返回本 worker 新增结果
    results: list[dict] = []
    events: list[dict] = []

    tool = TOOLS.get(tool_name)
    db = SessionLocal()
    try:
        record = AgentAction(
            id=action_id,
            session_id=state["session_id"],
            user_id=user_id,
            action_type=tool_name,
            tool_name=tool_name,
            params=params,
            risk_level=action.get("risk_level") or "read",
            status="pending",
            canvas_version=canvas_version,
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.flush()

        if not tool:
            data = {"error": "unknown tool"}
            record.status = "failed"
            record.result = data
            _write_result_message(db, state["session_id"], tool_name, False, data)
            db.commit()
            results.append({"tool": tool_name, "ok": False, "data": data})
            events.append({"type": "action_result", "actionId": action_id, "tool": tool_name, "ok": False, "data": data})
            agent_action_fail(state["session_id"], tool_name)
            return {"executed_results": results, "events": events}

        try:
            data = _call_tool(tool, canvas_id, user_id, params)
            ok = "error" not in data
            record.status = "executed" if ok else "failed"
            record.result = data
            _write_result_message(db, state["session_id"], tool_name, ok, data)
            db.commit()
            results.append({"tool": tool_name, "ok": ok, "data": data, "summary": action.get("summary")})
            events.append({"type": "action_result", "actionId": action_id, "tool": tool_name, "ok": ok, "data": data})
            if ok:
                agent_action_success(state["session_id"], tool_name, 1)
            else:
                agent_action_fail(state["session_id"], tool_name)
        except Exception as e:
            data = {"error": str(e)[:300]}
            record.status = "failed"
            record.result = data
            _write_result_message(db, state["session_id"], tool_name, False, data)
            db.commit()
            results.append({"tool": tool_name, "ok": False, "data": data})
            events.append({"type": "action_result", "actionId": action_id, "tool": tool_name, "ok": False, "data": data})
            agent_action_fail(state["session_id"], tool_name)
    finally:
        db.close()

    return {"executed_results": results, "events": events}
