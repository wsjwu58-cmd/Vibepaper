"""审批签发与原子消费。domain 不依赖 FastAPI；本层使用 SQLAlchemy Session。"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..core.config import settings
from ..domain.action_states import AWAITING_APPROVAL, APPROVED, REJECTED, EXPIRED
from ..domain.approval import (
    build_signed_token,
    compute_action_hash,
    default_expires_at,
    isoformat_utc,
    new_nonce,
    split_token,
    sign_payload,
    utcnow,
)
from ..domain.idempotency import derive_idempotency_key
from ..models import AgentAction, AgentApproval
from ..services.session_service import session_service


def signing_secret() -> str:
    secret = (settings.confirm_signing_secret or "").strip()
    if secret:
        return secret
    if (settings.environment or "").lower() == "production":
        raise RuntimeError("VIBEPAPER_CONFIRM_SIGNING_SECRET is required in production")
    return "dev-only-confirm-signing-secret-not-for-prod"


def issue_approval(
    db: Session,
    *,
    action: AgentAction,
    canvas_id: int | None,
    canvas_version: int,
    plan_version: int,
    tool_name: str,
    params: dict,
    estimated_cost: int,
    chain_estimated_cost: int,
    ttl_seconds: int | None = None,
) -> tuple[AgentApproval, str, dict[str, Any]]:
    child_cap = int(estimated_cost or 0) + int(chain_estimated_cost or 0)
    action_hash = compute_action_hash(tool_name, params, child_cap)
    nonce = new_nonce()
    expires_at = default_expires_at(ttl_seconds or settings.confirm_token_ttl_seconds)
    payload = {
        "actionId": str(action.id),
        "userId": str(action.user_id),
        "canvasId": str(canvas_id or ""),
        "canvasVersion": int(canvas_version or 0),
        "planVersion": int(plan_version or 1),
        "actionHash": action_hash,
        "estimatedCost": int(estimated_cost or 0),
        "chainEstimatedCost": int(chain_estimated_cost or 0),
        "expiresAt": isoformat_utc(expires_at),
        "nonce": nonce,
    }
    secret = signing_secret()
    signature = sign_payload(secret, payload)
    token = build_signed_token(secret, payload)

    approval = AgentApproval(
        id=session_service.next_id(),
        action_id=action.id,
        session_id=action.session_id,
        user_id=action.user_id,
        canvas_id=canvas_id,
        canvas_version=int(canvas_version or 0),
        plan_version=int(plan_version or 1),
        tool_name=tool_name,
        action_hash=action_hash,
        estimated_cost=int(estimated_cost or 0),
        chain_estimated_cost=int(chain_estimated_cost or 0),
        approved_cost_cap=child_cap,
        nonce=nonce,
        token_signature=signature,
        expires_at=expires_at,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(approval)
    action.status = AWAITING_APPROVAL
    action.confirm_token = token
    action.canvas_version = int(canvas_version or 0)
    action.plan_version = int(plan_version or 1)
    action.estimated_cost = int(estimated_cost or 0)
    action.approved_cost_cap = child_cap
    if not action.idempotency_key:
        action.idempotency_key = derive_idempotency_key(action.id, action.attempt_no or 1)
    db.flush()
    action.approval_id = approval.id
    payload_out = {
        **payload,
        "approvalToken": token,
        "approvedCostCap": child_cap,
    }
    return approval, token, payload_out


class ApprovalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def consume_approval(
    db: Session,
    *,
    token: str,
    user_id: int,
    session_id: int,
    action_id: int,
    canvas_id: int | None,
    canvas_version: int | None,
    plan_version: int | None,
    action_hash: str | None,
    accept: bool,
) -> AgentApproval:
    try:
        nonce, signature = split_token(token)
    except ValueError as exc:
        raise ApprovalError("INVALID_INPUT", "确认令牌格式无效") from exc

    row = (
        db.query(AgentApproval)
        .filter(AgentApproval.nonce == nonce, AgentApproval.action_id == action_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise ApprovalError("CONFIRMATION_REQUIRED", "确认令牌无效")
    if row.session_id != session_id or int(row.user_id) != int(user_id):
        raise ApprovalError("PERMISSION_DENIED", "无权确认该操作")
    if canvas_id is not None and row.canvas_id and int(row.canvas_id) != int(canvas_id):
        raise ApprovalError("PERMISSION_DENIED", "画布不匹配")
    if not hmac.compare_digest(row.token_signature, signature):
        raise ApprovalError("INVALID_INPUT", "确认令牌签名无效")

    now = utcnow()
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is not None and expires <= now:
        row.status = EXPIRED
        db.flush()
        raise ApprovalError("CONFIRM_EXPIRED", "确认已过期，请重新发送指令")

    if canvas_version is not None and int(row.canvas_version or 0) != int(canvas_version):
        raise ApprovalError("VERSION_CONFLICT", "画布版本已变化，请刷新后重新确认")
    if plan_version is not None and int(row.plan_version or 1) != int(plan_version):
        raise ApprovalError("VERSION_CONFLICT", "计划版本已变化，请重新确认")
    if action_hash and action_hash != row.action_hash:
        raise ApprovalError("VERSION_CONFLICT", "操作参数已变化，请重新确认")

    if row.consumed_at is not None or row.status in ("consumed", "rejected"):
        raise ApprovalError("INVALID_INPUT", "确认令牌已使用")

    if not accept:
        result = db.execute(
            update(AgentApproval)
            .where(
                AgentApproval.id == row.id,
                AgentApproval.consumed_at.is_(None),
                AgentApproval.status == "pending",
            )
            .values(consumed_at=now, status=REJECTED)
        )
        if result.rowcount != 1:
            raise ApprovalError("INVALID_INPUT", "确认令牌已使用")
        return row

    result = db.execute(
        update(AgentApproval)
        .where(
            AgentApproval.id == row.id,
            AgentApproval.consumed_at.is_(None),
            AgentApproval.status == "pending",
        )
        .values(consumed_at=now, status="consumed")
    )
    if result.rowcount != 1:
        raise ApprovalError("INVALID_INPUT", "确认令牌已使用")
    db.refresh(row)
    return row


def mark_action_approved(db: Session, action: AgentAction, approval: AgentApproval) -> None:
    action.status = APPROVED
    action.approval_id = approval.id
    action.approved_cost_cap = approval.approved_cost_cap
    db.flush()
