"""Alembic 迁移入口：启动时升级到 head。"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger("agent.schema")


def ensure_schema() -> None:
    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    command.upgrade(cfg, "head")
    logger.info("agent alembic migrations applied")
