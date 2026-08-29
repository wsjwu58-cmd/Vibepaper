"""Redis ZSET 时钟队列：Lua 原子认领，避免双消费者重复唤醒。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

CLAIM_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local n = tonumber(ARGV[2])
local due = redis.call('ZRANGEBYSCORE', key, '-inf', now, 'LIMIT', 0, n)
if #due == 0 then
  return {}
end
for i, member in ipairs(due) do
  redis.call('ZREM', key, member)
end
return due
"""

CLOCK_KEY = "agent_clock_jobs"


def claim_due_jobs(redis_client, *, now: float | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """原子取出并删除到期 job。返回解析后的 payload 列表。"""
    score = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    raw_items = redis_client.eval(CLAIM_LUA, 1, CLOCK_KEY, score, int(limit))
    jobs: list[dict[str, Any]] = []
    for item in raw_items or []:
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        try:
            jobs.append(json.loads(item))
        except (TypeError, json.JSONDecodeError):
            continue
    return jobs


def schedule_job(redis_client, payload: dict[str, Any], wakeup_at: float) -> None:
    redis_client.zadd(CLOCK_KEY, {json.dumps(payload, ensure_ascii=False): float(wakeup_at)})
