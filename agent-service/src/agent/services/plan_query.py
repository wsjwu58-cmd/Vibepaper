"""可审计计划摘要：动作、审批、等待任务。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AgentAction, AgentApproval, AgentSession


def get_plan_summary(db: Session, session: AgentSession, plan_version: int) -> dict:
    actions = (
        db.query(AgentAction)
        .filter(AgentAction.session_id == session.id, AgentAction.plan_version == int(plan_version))
        .order_by(AgentAction.id.asc())
        .all()
    )
    approvals = (
        db.query(AgentApproval)
        .filter(AgentApproval.session_id == session.id, AgentApproval.plan_version == int(plan_version))
        .order_by(AgentApproval.id.asc())
        .all()
    )
    waiting = [
        {
            "actionId": str(a.id),
            "tool": a.tool_name,
            "taskId": a.task_id,
            "status": a.status,
            "estimatedCost": int(a.estimated_cost or 0),
        }
        for a in actions
        if a.status in ("waiting_terminal", "accepted", "dispatching")
    ]
    return {
        "sessionId": str(session.id),
        "canvasId": str(session.canvas_id) if session.canvas_id else None,
        "planVersion": int(plan_version),
        "actions": [
            {
                "actionId": str(a.id),
                "stepId": a.step_id,
                "tool": a.tool_name,
                "status": a.status,
                "riskLevel": a.risk_level,
                "idempotencyKey": a.idempotency_key,
                "attemptNo": a.attempt_no,
                "approvalId": str(a.approval_id) if a.approval_id else None,
                "parentActionId": str(a.parent_action_id) if a.parent_action_id else None,
                "estimatedCost": int(a.estimated_cost or 0),
                "taskId": a.task_id,
                "errorCode": a.error_code,
            }
            for a in actions
        ],
        "approvals": [
            {
                "approvalId": str(p.id),
                "actionId": str(p.action_id),
                "status": p.status,
                "estimatedCost": int(p.estimated_cost or 0),
                "chainEstimatedCost": int(p.chain_estimated_cost or 0),
                "approvedCostCap": int(p.approved_cost_cap or 0),
                "expiresAt": p.expires_at.isoformat() if p.expires_at else None,
                "consumedAt": p.consumed_at.isoformat() if p.consumed_at else None,
            }
            for p in approvals
        ],
        "waitingTasks": waiting,
    }
