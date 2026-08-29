from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent.core.db import Base
from agent.domain.approval import compute_action_hash
from agent.domain.idempotency import derive_idempotency_key
from agent.domain.hashed_embedding import cosine_similarity, hashed_embedding
from agent.models import AgentAction, AgentSession
from agent.services.approval_service import ApprovalError, consume_approval, issue_approval
from agent.services.plan_query import get_plan_summary
from agent.services.resume_service import consume_terminal_event
from agent.services.review_service import review_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _action() -> AgentAction:
    return AgentAction(
        id=101,
        session_id=11,
        user_id=7,
        action_type="submit_generation",
        tool_name="submit_generation",
        params={"node_id": 22, "estimated_cost": 8},
        canvas_version=3,
        plan_version=1,
        idempotency_key=derive_idempotency_key(101),
        created_at=datetime.now(timezone.utc),
    )


def test_approval_token_is_bound_and_one_time(db):
    action = _action()
    db.add(action)
    db.flush()
    approval, token, _ = issue_approval(
        db,
        action=action,
        canvas_id=9,
        canvas_version=3,
        plan_version=1,
        tool_name="submit_generation",
        params=action.params,
        estimated_cost=8,
        chain_estimated_cost=0,
    )
    db.commit()

    consumed = consume_approval(
        db,
        token=token,
        user_id=7,
        session_id=11,
        action_id=101,
        canvas_id=9,
        canvas_version=3,
        plan_version=1,
        action_hash=compute_action_hash("submit_generation", action.params, 8),
        accept=True,
    )
    assert consumed.id == approval.id
    db.commit()

    with pytest.raises(ApprovalError, match="已使用"):
        consume_approval(
            db,
            token=token,
            user_id=7,
            session_id=11,
            action_id=101,
            canvas_id=9,
            canvas_version=3,
            plan_version=1,
            action_hash=compute_action_hash("submit_generation", action.params, 8),
            accept=True,
        )


def test_approval_rejects_changed_canvas_or_action(db):
    action = _action()
    db.add(action)
    db.flush()
    _, token, _ = issue_approval(
        db,
        action=action,
        canvas_id=9,
        canvas_version=3,
        plan_version=1,
        tool_name="submit_generation",
        params=action.params,
        estimated_cost=8,
        chain_estimated_cost=0,
    )
    db.commit()

    with pytest.raises(ApprovalError, match="画布版本"):
        consume_approval(
            db,
            token=token,
            user_id=7,
            session_id=11,
            action_id=101,
            canvas_id=9,
            canvas_version=4,
            plan_version=1,
            action_hash=compute_action_hash("submit_generation", action.params, 8),
            accept=True,
        )


def test_terminal_event_is_idempotent_and_marks_action(monkeypatch, db):
    db.add(AgentSession(
        id=11,
        user_id=7,
        canvas_id=9,
        title="test",
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    action = _action()
    action.task_id = "task-1"
    action.status = "waiting_terminal"
    db.add(action)
    db.commit()

    monkeypatch.setattr("agent.graph.app.run_agent_wakeup", lambda *args, **kwargs: [{"type": "task_status"}])
    body = {
        "task_id": "task-1",
        "node_id": 22,
        "canvas_id": 9,
        "user_id": 7,
        "status": "succeeded",
    }
    first = consume_terminal_event(db, body)
    second = consume_terminal_event(db, body)

    assert first["ok"] is True and first["duplicate"] is False
    assert second["ok"] is True and second["duplicate"] is True
    assert db.get(AgentAction, 101).status == "succeeded"


def test_action_idempotency_key_is_stable_per_attempt():
    assert derive_idempotency_key(88, 1) == "agt:88:1"
    assert derive_idempotency_key(88, 2) == "agt:88:2"


def test_hashed_embedding_preserves_token_dimensions_for_similarity():
    same_a = hashed_embedding("都市短剧 女主 红色风衣")
    same_b = hashed_embedding("红色风衣的都市短剧女主")
    different = hashed_embedding("太空飞船 星际战斗")

    assert cosine_similarity(same_a, same_b) > cosine_similarity(same_a, different)


def test_render_review_only_recommends_local_retry(db):
    result = review_service.record(
        db,
        7,
        {
            "canvasId": 9,
            "targetNodeId": 22,
            "targetKind": "clip",
            "scores": {"identity": 0.2},
            "retryCount": 0,
            "remainingCostCap": 10,
            "extraCost": 3,
        },
    )

    assert result["recommendedAction"] == "rerun_local"
    assert result["requiresConfirmation"] is True
    assert review_service.list(db, 7, 9)[0]["reviewId"] == result["reviewId"]


def test_plan_summary_returns_auditable_action_state(db):
    session = AgentSession(
        id=11,
        user_id=7,
        canvas_id=9,
        title="test",
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    action = _action()
    action.status = "waiting_terminal"
    action.task_id = "task-1"
    db.add_all([session, action])
    db.commit()

    summary = get_plan_summary(db, session, 1)

    assert summary["planVersion"] == 1
    assert summary["actions"][0]["idempotencyKey"] == "agt:101:1"
    assert summary["waitingTasks"][0]["taskId"] == "task-1"
