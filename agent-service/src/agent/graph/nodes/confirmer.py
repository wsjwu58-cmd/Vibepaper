"""confirmer：LangGraph interrupt 等待用户确认。"""

from __future__ import annotations

from datetime import datetime, timezone

from langgraph.types import interrupt

from ...core.db import SessionLocal
from ...models import AgentAction
from ...services.telemetry import agent_confirm_accept, agent_confirm_show
from ..confirm_helpers import (
    build_inline_confirm_text,
    should_auto_confirm,
)
from ..state import AgentState
from .risk_classifier import _next_id


def confirmer_node(state: AgentState) -> dict:
    pending = list(state.get("pending_high_risk") or [])
    if not pending:
        return {"confirm_accept": True, "executable_actions": state.get("executable_actions") or []}

    action = pending[0]
    if action.get("confirm_reason") == "contract_violation" or action.get("status") == "blocked":
        err = (state.get("contract_violations") or [{}])[0].get("error", "创作契约校验未通过")
        events = list(state.get("events") or [])
        events.append({"type": "contract_blocked", "tool": action.get("tool_name"), "error": err})
        return {
            "confirm_accept": False,
            "executable_actions": [],
            "pending_high_risk": [],
            "reply": err,
            "events": events,
        }

    action_id = int(action.get("action_id") or _next_id())
    canvas_version = int(state.get("canvas_version") or 1)
    params = action.get("params") or {}
    estimated_cost = int(params.get("estimated_cost") or params.get("estimatedCost") or 0)
    # 整体确认：提交生成时顺带预估「后续就绪节点自动提交」的点数
    chain_cost = int(params.get("chain_estimated_cost") or 0)
    if not chain_cost and action.get("tool_name") == "submit_generation" and params.get("node_id"):
        from ...tools.registry import _coerce_node_id
        nid = _coerce_node_id(params.get("node_id"))
        if nid:
            canvas_ctx = state.get("canvas_context") or {}
            try:
                from ...domain.dependency_scheduler import estimate_downstream_cost
                chain_cost = estimate_downstream_cost(nid, canvas_ctx)
            except (TypeError, ValueError):
                chain_cost = 0
    node_ids = list(params.get("node_ids") or [])
    if params.get("node_id") is not None:
        # 占位符也展示，但不做 int 强转（Snowflake / $created[N]）
        node_ids = [params["node_id"]]

    db = SessionLocal()
    try:
        record = db.get(AgentAction, action_id)
        if record is None:
            db.add(AgentAction(
                id=action_id,
                session_id=state["session_id"],
                user_id=state["user_id"],
                action_type=action["tool_name"],
                tool_name=action["tool_name"],
                params=params,
                risk_level="high",
                confirm_reason=action.get("confirm_reason"),
                status="pending",
                confirm_token=f"lg:{state['session_id']}:{action_id}",
                canvas_version=canvas_version,
                created_at=datetime.now(timezone.utc),
            ))
        else:
            record.status = "pending"
            record.params = params
            record.confirm_token = f"lg:{state['session_id']}:{action_id}"
            record.canvas_version = canvas_version
            record.confirm_reason = action.get("confirm_reason")
        db.commit()
    finally:
        db.close()

    payload = {
        "type": "confirm_required",
        # 字符串化，避免 SSE JSON 数字在浏览器丢 Snowflake 精度
        "actionId": str(action_id),
        "tool": action["tool_name"],
        "summary": action.get("summary") or action["tool_name"],
        "confirmReason": action.get("confirm_reason"),
        "token": f"lg:{state['session_id']}:{action_id}",
        "estimatedCost": estimated_cost,
        "chainEstimatedCost": chain_cost,
        "estimatedTotalCost": estimated_cost + chain_cost,
        "affectedNodeCount": len(node_ids) if node_ids else 1,
        "canvasVersion": canvas_version,
        "impact": {
            "nodeIds": [str(x) for x in node_ids] if node_ids else [],
            "estimatedCost": estimated_cost,
            "chainEstimatedCost": chain_cost,
            "tool": action["tool_name"],
        },
    }
    user_content = state.get("user_content") or ""
    auto_accept = should_auto_confirm(user_content, action["tool_name"])
    events = list(state.get("events") or [])

    if auto_accept:
        accept = True
        agent_confirm_accept(state["session_id"], action["tool_name"])
        events.append({
            "type": "inline_confirm",
            "accepted": True,
            "content": build_inline_confirm_text(action, accepted=True, chain_cost=chain_cost),
            "actionId": str(action_id),
        })
        db2 = SessionLocal()
        try:
            rec = db2.get(AgentAction, action_id)
            if rec:
                rec.status = "confirmed"
                db2.commit()
        finally:
            db2.close()
    else:
        agent_confirm_show(
            state["session_id"], action["tool_name"], action.get("confirm_reason"),
            estimated_cost=estimated_cost,
        )
        payload["dialogConfirm"] = True
        events.append(payload)
        decision = interrupt(payload)
        accept = bool(decision.get("accept")) if isinstance(decision, dict) else bool(decision)
        if accept:
            agent_confirm_accept(state["session_id"], action["tool_name"])
        events.append({
            "type": "inline_confirm",
            "accepted": accept,
            "content": build_inline_confirm_text(action, accepted=accept, chain_cost=chain_cost),
            "actionId": str(action_id),
        })

    if accept:
        to_run = [{**action, "action_id": action_id, "status": "ready"}]
        return {
            "confirm_accept": True,
            "executable_actions": list(state.get("executable_actions") or []) + to_run,
            "pending_high_risk": pending[1:],
            "pending_confirm": None if auto_accept else payload,
            "events": events,
        }
    return {
        "confirm_accept": False,
        "executable_actions": [],
        "pending_high_risk": [],
        "pending_confirm": payload,
        "reply": f"已取消操作：{action.get('summary') or action['tool_name']}",
        "events": events,
    }
