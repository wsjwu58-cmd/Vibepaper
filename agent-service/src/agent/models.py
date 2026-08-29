from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .core.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    canvas_id = Column(BigInteger, index=True)
    title = Column(String(128), default="新对话")
    skill_id = Column(BigInteger)
    token_used_total = Column(Integer, default=0)
    points_used_total = Column(Integer, default=0)
    model_usage = Column(JSON, default=dict)
    status = Column(String(16), default="active")
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user / assistant / system
    msg_type = Column(String(16), default="text")  # text / action / confirm / result
    content = Column(Text)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_agent_actions_idempotency_key"),
        Index("ix_agent_actions_step", "session_id", "plan_version", "step_id", unique=True),
        Index("ix_agent_actions_task", "task_id"),
    )

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    action_type = Column(String(64), nullable=False)
    tool_name = Column(String(64))
    params = Column(JSON, default=dict)
    risk_level = Column(String(16), default="low")
    confirm_reason = Column(String(128))
    # planned / awaiting_approval / approved / dispatching / accepted /
    # waiting_terminal / succeeded / failed / cancelled / rejected / expired
    status = Column(String(32), default="planned")
    confirm_token = Column(String(256))
    canvas_version = Column(Integer)
    result = Column(JSON)
    error_code = Column(String(64))
    idempotency_key = Column(String(128))
    plan_version = Column(Integer, default=1)
    step_id = Column(String(64))
    approval_id = Column(BigInteger)
    attempt_no = Column(Integer, default=1)
    parent_action_id = Column(BigInteger)
    estimated_cost = Column(Integer, default=0)
    approved_cost_cap = Column(Integer)
    task_id = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_agent_approvals_nonce"),
        Index("ix_agent_approvals_action", "action_id"),
    )

    id = Column(BigInteger, primary_key=True)
    action_id = Column(BigInteger, nullable=False)
    session_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    canvas_id = Column(BigInteger)
    canvas_version = Column(Integer, nullable=False)
    plan_version = Column(Integer, nullable=False, default=1)
    tool_name = Column(String(64), nullable=False)
    action_hash = Column(String(64), nullable=False)
    estimated_cost = Column(Integer, nullable=False, default=0)
    chain_estimated_cost = Column(Integer, nullable=False, default=0)
    approved_cost_cap = Column(Integer, nullable=False, default=0)
    nonce = Column(String(64), nullable=False)
    token_signature = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    status = Column(String(16), nullable=False, default="pending")  # pending/consumed/rejected/expired
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AgentWakeupNotice(Base):
    __tablename__ = "agent_wakeup_notices"
    __table_args__ = (
        UniqueConstraint("session_id", "task_id", "terminal_status", name="uq_wakeup_session_task_status"),
    )

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, nullable=False)
    task_id = Column(String(64), nullable=False)
    terminal_status = Column(String(32), nullable=False)
    canvas_id = Column(BigInteger)
    node_id = Column(BigInteger)
    user_id = Column(BigInteger)
    payload = Column(JSON, default=dict)
    processing_at = Column(DateTime(timezone=True))
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class RenderReview(Base):
    __tablename__ = "render_reviews"
    __table_args__ = (
        Index("ix_render_reviews_canvas_node", "canvas_id", "target_node_id"),
    )

    id = Column(BigInteger, primary_key=True)
    canvas_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    target_node_id = Column(BigInteger, nullable=False)
    target_kind = Column(String(32), default="clip")  # keyframe / clip / episode
    scores = Column(JSON, default=dict)
    failures = Column(JSON, default=list)
    recommended_action = Column(String(64))
    evidence = Column(JSON, default=dict)
    retry_count = Column(Integer, default=0)
    status = Column(String(16), default="pending")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(BigInteger, primary_key=True)
    owner_id = Column(BigInteger, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    instructions = Column(Text)
    source = Column(String(32), default="manual")  # manual / from_conversation / upload / builtin
    category = Column(String(32), default="general")  # image / video / text / canvas / general
    version = Column(Integer, default=1)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger)
    canvas_id = Column(BigInteger, index=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String(32), default="preference")  # preference/style/habit
    scope = Column(String(16), default="long_term")  # long_term / daily / project / session
    visibility = Column(String(16), default="user")  # user / project / enterprise
    source = Column(String(64), default="user")
    confidence = Column(Float, default=1.0)
    embedding = Column(JSON, default=list)
    expires_at = Column(DateTime(timezone=True))
    deleted = Column(Boolean, default=False)
    last_merged_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SessionFragment(Base):
    __tablename__ = "session_fragments"

    id = Column(BigInteger, primary_key=True)
    owner_id = Column(BigInteger, nullable=False, index=True)
    title = Column(String(128))
    content = Column(JSON, default=list)
    canvas_id = Column(BigInteger)
    fragment_type = Column(String(32), default="worldview")  # worldview/character/style/plot/status
    created_at = Column(DateTime(timezone=True), default=utcnow)
