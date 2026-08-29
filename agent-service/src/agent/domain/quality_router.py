"""质量门禁路由：低于阈值只重跑受影响节点；连续失败两次进入人工确认。"""

from __future__ import annotations

from typing import Any

from .drama_schema import RenderReview

DEFAULT_THRESHOLDS = {
    "identity": 0.72,
    "costume": 0.70,
    "composition": 0.65,
    "motion": 0.60,
    "screen_direction": 0.70,
    "duration": 0.80,
    "sync": 0.75,
    "continuity": 0.72,
}

MAX_AUTO_RETRY = 2


def route_review(
    review: RenderReview | dict[str, Any],
    *,
    remaining_cost_cap: int | None = None,
    extra_cost: int = 0,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    data = review if isinstance(review, dict) else review.model_dump()
    scores = dict(data.get("scores") or {})
    failures = list(data.get("failures") or [])
    retry_count = int(data.get("retry_count") or 0)
    kind = str(data.get("target_kind") or "clip")
    bars = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    for key, bar in bars.items():
        if key in scores and float(scores[key]) < bar and key not in failures:
            failures.append(key)

    if not failures and all((float(scores.get(k, 1.0)) >= bars.get(k, 0) for k in scores)):
        return {
            "action": "accept",
            "rerun_unit": None,
            "reason": "quality_pass",
            "failures": [],
        }

    if remaining_cost_cap is not None and int(extra_cost) > int(remaining_cost_cap):
        return {
            "action": "human_review",
            "rerun_unit": None,
            "reason": "budget_exceeded",
            "failures": failures,
        }

    if retry_count >= MAX_AUTO_RETRY:
        return {
            "action": "human_review",
            "rerun_unit": None,
            "reason": "retry_exhausted",
            "failures": failures,
        }

    rerun_unit = "clip"
    if kind == "keyframe" or any(k in failures for k in ("identity", "costume", "composition")):
        rerun_unit = "keyframe"
    elif any(k in failures for k in ("sync",)):
        rerun_unit = "audio"
    elif kind == "episode":
        rerun_unit = "shot"

    return {
        "action": "rerun_local",
        "rerun_unit": rerun_unit,
        "reason": "quality_gate",
        "failures": failures,
    }
