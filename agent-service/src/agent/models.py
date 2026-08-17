from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, String, Text

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

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    action_type = Column(String(64), nullable=False)
    tool_name = Column(String(64))
    params = Column(JSON, default=dict)
    risk_level = Column(String(16), default="low")
    confirm_reason = Column(String(128))
    status = Column(String(16), default="pending")  # pending/executed/failed/cancelled
    confirm_token = Column(String(128))
    canvas_version = Column(Integer)
    result = Column(JSON)
    error_code = Column(String(64))
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
    content = Column(Text, nullable=False)
    memory_type = Column(String(32), default="preference")  # preference/style/habit
    scope = Column(String(16), default="long_term")  # long_term / daily
    embedding = Column(JSON, default=list)  # 简单词频向量（pgvector 可替换）
    last_merged_at = Column(DateTime(timezone=True))  # 子 Agent 最后去重合并时间
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
