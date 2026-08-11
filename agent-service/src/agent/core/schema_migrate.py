"""轻量 schema 补丁：为已有库补齐记忆/Skill 相关列（无 Alembic 时）。"""

from __future__ import annotations

import logging

from sqlalchemy import text

from .db import engine

logger = logging.getLogger("agent.schema")

_PATCHES = [
    "ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS scope VARCHAR(16) DEFAULT 'long_term'",
    "ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS embedding JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS last_merged_at TIMESTAMPTZ",
    "ALTER TABLE session_fragments ADD COLUMN IF NOT EXISTS fragment_type VARCHAR(32) DEFAULT 'worldview'",
    "ALTER TABLE session_fragments ADD COLUMN IF NOT EXISTS canvas_id BIGINT",
]


def ensure_schema():
    with engine.begin() as conn:
        for sql in _PATCHES:
            try:
                conn.execute(text(sql))
            except Exception as e:
                logger.warning("schema patch skipped: %s (%s)", sql, e)
    logger.info("agent schema patches applied")
