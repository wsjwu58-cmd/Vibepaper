from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from .core.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    node_id = Column(BigInteger, index=True)
    canvas_id = Column(BigInteger, index=True)
    model_type = Column(String(64), nullable=False, index=True)
    model_params = Column(JSON, default=dict)
    estimated_cost = Column(Integer, nullable=False)
    actual_cost = Column(Integer, default=0)
    status = Column(String(16), nullable=False, default="queued", index=True)  # queued/running/succeeded/failed/cancelled/expired/settlement_error
    error_code = Column(String(64))
    error_message = Column(Text)
    retryable = Column(Boolean, default=False)
    source = Column(String(16), default="user")
    pricing_version = Column(Integer, default=1)
    freeze_deadline = Column(DateTime(timezone=True))
    attempts = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TaskAttempt(Base):
    __tablename__ = "task_attempts"

    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, nullable=False, index=True)
    attempt_no = Column(Integer, default=1)
    provider = Column(String(64))
    status = Column(String(16))
    error_code = Column(String(64))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))


class TaskOutput(Base):
    __tablename__ = "task_outputs"

    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, nullable=False, index=True)
    output_type = Column(String(16), nullable=False)
    url = Column(Text)
    content_type = Column(String(64))
    file_path = Column(Text)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    model_type = Column(String(16), nullable=False, index=True)  # text/image/video/audio
    display_name = Column(String(128))
    description = Column(Text)
    provider = Column(String(64), default="mock")
    base_url = Column(Text)
    api_key_ref = Column(String(64))
    enabled = Column(Boolean, default=True, index=True)
    default_params = Column(JSON, default=dict)
    base_price = Column(Integer, default=10)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PricingRule(Base):
    __tablename__ = "pricing_rules"
    __table_args__ = (UniqueConstraint("model_id", "rule_key", "rule_value", name="uq_pricing_model_rule"),)

    id = Column(BigInteger, primary_key=True)
    model_id = Column(BigInteger, nullable=False, index=True)
    rule_key = Column(String(64), nullable=False)
    rule_value = Column(String(64), nullable=False)
    points = Column(Integer, nullable=False)
