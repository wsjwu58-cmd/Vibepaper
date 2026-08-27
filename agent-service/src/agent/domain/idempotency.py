"""业务幂等键：由 action_id + attempt_no 派生，禁止随机 UUID。"""

from __future__ import annotations


def derive_idempotency_key(action_id: int, attempt_no: int = 1) -> str:
    """固定公式：agt:{action_id}:{attempt_no}。"""
    aid = int(action_id)
    attempt = max(1, int(attempt_no or 1))
    return f"agt:{aid}:{attempt}"


def parse_idempotency_key(key: str) -> tuple[int, int] | None:
    raw = (key or "").strip()
    if not raw.startswith("agt:"):
        return None
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except (TypeError, ValueError):
        return None
