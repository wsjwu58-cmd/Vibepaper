"""generation 终态事件：幂等写入 notice 后唤醒 wakeup 子图。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import AgentAction, AgentSession, AgentWakeupNotice
from ..services.session_service import session_service

logger = logging.getLogger("agent.resume")

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "expired", "settlement_error"})


def _as_int(value) -> int | None:
    if value is None or value is False:
        return None
    try:
        n = int(value)
        return n if n != 0 else None
    except (TypeError, ValueError):
        return None


def consume_terminal_event(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    status = str(body.get("status") or "").lower()
    if status not in TERMINAL:
        return {"ok": False, "error_code": "INVALID_INPUT", "message": "非终态事件"}

    task_id = str(body.get("task_id") or body.get("taskId") or "").strip()
    if not task_id:
        return {"ok": False, "error_code": "INVALID_INPUT", "message": "缺少 task_id"}

    user_id = _as_int(body.get("user_id") or body.get("userId"))
    canvas_id = _as_int(body.get("canvas_id") or body.get("canvasId"))
    node_id = _as_int(body.get("node_id") or body.get("nodeId"))

    session_id = _as_int(body.get("session_id") or body.get("sessionId"))
    if session_id is None:
        session_id = _resolve_session_id(db, user_id, canvas_id, task_id)
    if session_id is None:
        return {"ok": True, "duplicate": False, "skipped": True, "reason": "no_session"}

    now = datetime.now(timezone.utc)
    notice = (
        db.query(AgentWakeupNotice)
        .filter(
            AgentWakeupNotice.session_id == session_id,
            AgentWakeupNotice.task_id == task_id,
            AgentWakeupNotice.terminal_status == status,
        )
        .with_for_update()
        .first()
    )
    if notice is None:
        notice = AgentWakeupNotice(
            id=session_service.next_id(),
            session_id=session_id,
            task_id=task_id,
            terminal_status=status,
            canvas_id=canvas_id,
            node_id=node_id,
            user_id=user_id,
            payload={
                "error_code": body.get("error_code") or body.get("errorCode"),
                "model_type": body.get("model_type") or body.get("modelType"),
            },
            created_at=now,
        )
        db.add(notice)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            notice = (
                db.query(AgentWakeupNotice)
                .filter(
                    AgentWakeupNotice.session_id == session_id,
                    AgentWakeupNotice.task_id == task_id,
                    AgentWakeupNotice.terminal_status == status,
                )
                .with_for_update()
                .first()
            )
            if notice is None:
                return {"ok": False, "error_code": "EVENT_CONFLICT", "message": "终态事件去重冲突"}

    if notice.processed_at is not None:
        return {"ok": True, "duplicate": True, "sessionId": str(session_id), "taskId": task_id}
    processing = notice.processing_at
    if processing is not None:
        if processing.tzinfo is None:
            processing = processing.replace(tzinfo=timezone.utc)
        if processing > now - timedelta(minutes=5):
            return {
                "ok": True,
                "duplicate": True,
                "inProgress": True,
                "sessionId": str(session_id),
                "taskId": task_id,
            }
    notice.processing_at = now
    db.commit()

    _mark_action_terminal(db, session_id, task_id, status)

    from ..graph.app import run_agent_wakeup

    note = {
        "task_id": task_id,
        "node_id": node_id,
        "session_id": session_id,
        "user_id": user_id,
        "canvas_id": canvas_id,
        "model_type": body.get("model_type") or body.get("modelType"),
        "status": status,
        "source": "generation_terminal",
        "workflow_auto_submit": True,
    }
    try:
        events = run_agent_wakeup(session_id, int(user_id or 0), canvas_id, note)
    except Exception:
        logger.exception("agent wakeup failed session=%s task=%s", session_id, task_id)
        notice.processing_at = None
        db.commit()
        return {
            "ok": False,
            "error_code": "WAKEUP_FAILED",
            "message": "Agent 唤醒失败，可重试",
            "retryable": True,
        }
    notice.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "ok": True,
        "duplicate": False,
        "sessionId": str(session_id),
        "taskId": task_id,
        "events": len(events or []),
    }


def _resolve_session_id(db: Session, user_id: int | None, canvas_id: int | None, task_id: str) -> int | None:
    if task_id:
        row = (
            db.query(AgentAction)
            .filter(AgentAction.task_id == task_id)
            .order_by(AgentAction.id.desc())
            .first()
        )
        if row:
            return int(row.session_id)
    q = db.query(AgentSession).filter(AgentSession.status == "active")
    if user_id:
        q = q.filter(AgentSession.user_id == user_id)
    if canvas_id:
        q = q.filter(AgentSession.canvas_id == canvas_id)
    session = q.order_by(AgentSession.updated_at.desc()).first()
    return int(session.id) if session else None


def _mark_action_terminal(db: Session, session_id: int, task_id: str, status: str) -> None:
    row = (
        db.query(AgentAction)
        .filter(AgentAction.session_id == session_id, AgentAction.task_id == str(task_id))
        .order_by(AgentAction.id.desc())
        .first()
    )
    if not row:
        return
    if status == "succeeded":
        row.status = "succeeded"
    elif status in ("failed", "settlement_error"):
        row.status = "failed"
        row.error_code = row.error_code or "TOOL_ERROR"
    elif status == "cancelled":
        row.status = "cancelled"
    elif status == "expired":
        row.status = "expired"
    db.commit()
