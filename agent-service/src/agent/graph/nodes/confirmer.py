"""高风险动作：签发签名令牌 + LangGraph interrupt；禁止自动确认。"""

from __future__ import annotations

from datetime import datetime, timezone

from langgraph.types import interrupt

from ...core.db import SessionLocal
from ...domain.idempotency import derive_idempotency_key
from ...models import AgentAction
from ...services.approval_service import issue_approval
from ...services.telemetry import agent_confirm_accept, agent_confirm_show
from ..confirm_helpers import build_inline_confirm_text
from ..state import AgentState
from .risk_classifier import _next_id


def confirmer_node(state: AgentState) -> dict:
    pending = list(state.get("pending_high_risk") or [])
    if not pending:
        return {"confirm_accept": True, "executable_actions": state.get("executable_actions") or []}

    action = pending[0]
    if action.get("confirm_reason") == "contract_violation" or action.get("status") == "blocked":
        err = (state.get("contract_violations") or [{}])[0].get("error", "创作契约校验未通过")
        return {
            "confirm_accept": False,
            "executable_actions": [],
            "pending_high_risk": [],
            "reply": err,
            "events": [{"type": "contract_blocked", "tool": action.get("tool_name"), "error": err}],
        }

    action_id = int(action.get("action_id") or _next_id())
    canvas_version = int(state.get("canvas_version") or 1)
    plan_version = int((state.get("plan") or {}).get("version") or state.get("run_version") or 1)
    params = dict(action.get("params") or {})
    estimated_cost = int(params.get("estimated_cost") or params.get("estimatedCost") or 0)
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
        node_ids = [params["node_id"]]

    db = SessionLocal()
    try:
        record = db.get(AgentAction, action_id)
        if record is None:
            record = AgentAction(
                id=action_id,
                session_id=state["session_id"],
                user_id=state["user_id"],
                action_type=action["tool_name"],
                tool_name=action["tool_name"],
                params=params,
                risk_level="high",
                confirm_reason=action.get("confirm_reason"),
                status="planned",
                canvas_version=canvas_version,
                plan_version=plan_version,
                step_id=action.get("step_id"),
                estimated_cost=estimated_cost,
                idempotency_key=derive_idempotency_key(action_id, 1),
                created_at=datetime.now(timezone.utc),
            )
            db.add(record)
        else:
            record.params = params
            record.canvas_version = canvas_version
            record.plan_version = plan_version
            record.confirm_reason = action.get("confirm_reason")
            record.estimated_cost = estimated_cost
            if not record.idempotency_key:
                record.idempotency_key = derive_idempotency_key(record.id, record.attempt_no or 1)
        db.flush()

        approval, token, approval_payload = issue_approval(
            db,
            action=record,
            canvas_id=state.get("canvas_id"),
            canvas_version=canvas_version,
            plan_version=plan_version,
            tool_name=action["tool_name"],
            params=params,
            estimated_cost=estimated_cost,
            chain_estimated_cost=chain_cost,
        )
        db.commit()
    finally:
        db.close()

    payload = {
        "type": "confirm_required",
        "actionId": str(action_id),
        "tool": action["tool_name"],
        "summary": action.get("summary") or action["tool_name"],
        "confirmReason": action.get("confirm_reason"),
        "approvalToken": token,
        "token": token,
        "estimatedCost": estimated_cost,
        "chainEstimatedCost": chain_cost,
        "estimatedTotalCost": estimated_cost + chain_cost,
        "approvedCostCap": approval.approved_cost_cap,
        "affectedNodeCount": len(node_ids) if node_ids else 1,
        "canvasVersion": canvas_version,
        "planVersion": plan_version,
        "expiresAt": approval_payload.get("expiresAt"),
        "actionHash": approval_payload.get("actionHash"),
        "impact": {
            "nodeIds": [str(x) for x in node_ids] if node_ids else [],
            "estimatedCost": estimated_cost,
            "chainEstimatedCost": chain_cost,
            "tool": action["tool_name"],
        },
        "requiresConfirmationCard": True,
    }
    events: list[dict] = []

    agent_confirm_show(
        state["session_id"], action["tool_name"], action.get("confirm_reason"),
        estimated_cost=estimated_cost,
        action_id=action_id,
    )
    events.append(payload)
    decision = interrupt(payload)
    accept = bool(decision.get("accept")) if isinstance(decision, dict) else bool(decision)
    confirmed = None
    if isinstance(decision, dict):
        confirmed = decision.get("confirmedAction") or decision.get("confirmed_action") or decision.get("params")
        if confirmed is not None and not isinstance(confirmed, dict):
            confirmed = None

    if accept:
        agent_confirm_accept(state["session_id"], action["tool_name"], action_id=action_id)
        if confirmed:
            from ...domain.precedence import apply_confirmed_action
            params = apply_confirmed_action(params, confirmed)
            action = {**action, "params": params}
            db2 = SessionLocal()
            try:
                rec = db2.get(AgentAction, action_id)
                if rec:
                    rec.params = params
                    db2.commit()
            finally:
                db2.close()
    events.append({
        "type": "inline_confirm",
        "accepted": accept,
        "content": build_inline_confirm_text(action, accepted=accept, chain_cost=chain_cost),
        "actionId": str(action_id),
    })

    if accept:
        to_run = [{**action, "action_id": action_id, "status": "ready", "approval_id": approval.id}]
        return {
            "confirm_accept": True,
            "executable_actions": list(state.get("executable_actions") or []) + to_run,
            "pending_high_risk": pending[1:],
            "pending_confirm": payload,
            "react_mode": False,
            "react_decision": "finish",
            "events": events,
        }
    return {
        "confirm_accept": False,
        "executable_actions": [],
        "pending_high_risk": [],
        "pending_confirm": payload,
        "react_mode": False,
        "react_decision": "finish",
        "reply": f"已取消操作：{action.get('summary') or action['tool_name']}",
        "events": events,
    }
