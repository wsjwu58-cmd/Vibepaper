"""Agent 埋点事件（文档 §5.6）+ admin-service 分析接入。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import redis

from ..core.config import settings

logger = logging.getLogger("agent.telemetry")
_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)

STREAM_KEY = "agent_telemetry_events"


def _post_admin(event: str, payload: dict) -> None:
    base = (settings.admin_base_url or "").strip()
    if not base:
        return
    try:
        httpx.post(
            f"{base.rstrip('/')}/internal/analytics-events",
            json={"eventName": event, "payload": payload},
            timeout=5,
            trust_env=False,
        )
    except Exception as e:
        logger.debug("admin analytics post failed: %s", e)


def emit(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in fields.items() if v is not None},
    }
    logger.info("telemetry %s", json.dumps(payload, ensure_ascii=False, default=str))
    try:
        _redis.xadd(STREAM_KEY, {"payload": json.dumps(payload, ensure_ascii=False, default=str)}, maxlen=10000)
    except Exception:
        pass
    _post_admin(event, payload)


def agent_action_success(session_id: int, action_type: str, node_count_affected: int = 0, **extra: Any):
    emit("agent_action_success", session_id=session_id, action_type=action_type,
         node_count_affected=node_count_affected, **extra)


def agent_action_fail(session_id: int, action_type: str, error_code: str = "TOOL_ERROR", **extra: Any):
    emit("agent_action_fail", session_id=session_id, action_type=action_type, error_code=error_code, **extra)


def agent_confirm_show(session_id: int, action_type: str, confirm_reason: str | None = None, **extra: Any):
    emit("agent_confirm_show", session_id=session_id, action_type=action_type,
         confirm_reason=confirm_reason, **extra)


def agent_confirm_accept(session_id: int, action_type: str, **extra: Any):
    emit("agent_confirm_accept", session_id=session_id, action_type=action_type, **extra)


def agent_confirm_reject(session_id: int, action_type: str, **extra: Any):
    emit("agent_confirm_reject", session_id=session_id, action_type=action_type, **extra)


def clock_wakeup(session_id: int, task_id: str | None = None, **extra: Any):
    emit("clock_wakeup", session_id=session_id, task_id=task_id, **extra)


def memory_updated(user_id: int, scope: str, **extra: Any):
    emit("memory_updated", user_id=user_id, scope=scope, **extra)


def skill_loaded(session_id: int, skill_name: str, **extra: Any):
    emit("skill_loaded", session_id=session_id, skill_name=skill_name, **extra)

