"""会话级 SSE 事件发布（Redis Pub/Sub + 通知队列）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from ..core.config import settings

logger = logging.getLogger("agent.session_events")

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)

SSE_CHANNEL_PREFIX = "agent_session_sse:"
NOTIFY_LIST_PREFIX = "agent_session_notify:"


def publish_session_event(session_id: int, event: dict[str, Any]) -> None:
    """推送到 SSE 订阅者与通知队列（兼容 pull）。"""
    if not session_id:
        return
    payload = json.dumps(event, ensure_ascii=False, default=str)
    try:
        _redis.publish(f"{SSE_CHANNEL_PREFIX}{session_id}", payload)
        _redis.lpush(f"{NOTIFY_LIST_PREFIX}{session_id}", payload)
        _redis.ltrim(f"{NOTIFY_LIST_PREFIX}{session_id}", 0, 99)
        _redis.expire(f"{NOTIFY_LIST_PREFIX}{session_id}", 3600)
    except Exception as e:
        logger.debug("publish_session_event failed: %s", e)


def sse_channel(session_id: int) -> str:
    return f"{SSE_CHANNEL_PREFIX}{session_id}"
