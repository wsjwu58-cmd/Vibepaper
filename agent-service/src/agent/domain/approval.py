"""签名一次性确认令牌：绑定用户/画布版本/动作摘要，原子消费。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .action_states import HIGH_RISK_TOOLS

PARAM_DELTA_THRESHOLD = 0.30


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def normalize_params(params: dict | None) -> dict:
    raw = dict(params or {})
    # 去掉确认过程中的瞬时字段，保证哈希稳定
    for k in ("approval_token", "approvalToken", "confirm_token", "confirmToken"):
        raw.pop(k, None)
    return json.loads(_canonical_json(raw))


def compute_action_hash(tool_name: str, params: dict | None, child_cost_cap: int = 0) -> str:
    payload = {
        "tool": tool_name,
        "params": normalize_params(params),
        "childCostCap": int(child_cost_cap or 0),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def param_change_ratio(old_params: dict | None, new_params: dict | None) -> float:
    """粗略参数变化率：变更键数 / 并集。用于 30% 确认阈值。"""
    old = normalize_params(old_params)
    new = normalize_params(new_params)
    keys = set(old) | set(new)
    if not keys:
        return 0.0
    changed = 0
    for k in keys:
        if old.get(k) != new.get(k):
            changed += 1
    return changed / len(keys)


def requires_new_approval(
    *,
    tool_name: str,
    old_params: dict | None,
    new_params: dict | None,
    old_cost: int,
    new_cost: int,
    remaining_cap: int | None,
) -> bool:
    if tool_name in HIGH_RISK_TOOLS and tool_name == "change_model":
        return True
    if (new_params or {}).get("switchModel") or (new_params or {}).get("model") != (old_params or {}).get("model"):
        if (new_params or {}).get("model") and (old_params or {}).get("model"):
            if (new_params or {}).get("model") != (old_params or {}).get("model"):
                return True
    if param_change_ratio(old_params, new_params) >= PARAM_DELTA_THRESHOLD:
        return True
    if remaining_cap is not None and int(new_cost) > int(remaining_cap):
        return True
    if old_cost > 0 and abs(int(new_cost) - int(old_cost)) / old_cost >= PARAM_DELTA_THRESHOLD:
        return True
    return False


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def sign_payload(secret: str, payload: dict) -> str:
    body = _canonical_json(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_signed_token(secret: str, payload: dict) -> str:
    sig = sign_payload(secret, payload)
    nonce = payload["nonce"]
    return f"{nonce}.{sig}"


def split_token(token: str) -> tuple[str, str]:
    raw = (token or "").strip()
    if "." not in raw:
        raise ValueError("malformed token")
    nonce, sig = raw.split(".", 1)
    if not nonce or not sig:
        raise ValueError("malformed token")
    return nonce, sig


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_expires_at(ttl_seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=max(30, int(ttl_seconds or 300)))


def isoformat_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
