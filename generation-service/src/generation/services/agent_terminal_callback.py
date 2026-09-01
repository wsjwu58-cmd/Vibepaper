"""Builds the authenticated, task-scoped callback sent to the Pi Agent service."""

from typing import Any


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "expired", "settlement_error"}


def build_agent_terminal_callback(
    base_url: str,
    task: Any,
    status: str,
    environment: str,
    internal_service_token: str,
    outputs: list[Any] | None = None,
) -> dict[str, Any] | None:
    if status not in TERMINAL_STATUSES:
        return None
    base = (base_url or "").rstrip("/")
    if not base:
        return None
    token = (internal_service_token or "").strip()
    if environment in {"production", "staging"} and not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN_MISSING")
    headers = {"X-Internal-Service-Token": token} if token else {}
    output: dict[str, Any] = {}
    if outputs:
        first = outputs[0]
        if isinstance(first, dict):
            output = {key: first[key] for key in ("url", "contentType", "meta") if first.get(key) is not None}
        else:
            for key in ("url", "content_type", "meta"):
                value = getattr(first, key, None)
                if value is not None:
                    output[key] = value
    payload = {
        "type": "generation_terminal",
        "task_id": _string_id(task.id),
        "node_id": _string_id(getattr(task, "node_id", None)),
        "canvas_id": _string_id(getattr(task, "canvas_id", None)),
        "user_id": _string_id(getattr(task, "user_id", None)),
        "status": status,
        "error_code": getattr(task, "error_code", None),
        "model_type": getattr(task, "model_type", None),
        "actual_cost": getattr(task, "actual_cost", None),
    }
    if output:
        payload["output"] = output
    return {
        "url": f"{base}/internal/agent/resume",
        "headers": headers,
        "json": payload,
    }


def _string_id(value: Any) -> str | None:
    """跨服务 ID 统一以字符串传输，避免 JSON number 被 Agent 合同拒绝。"""
    if value is None:
        return None
    return str(value)
