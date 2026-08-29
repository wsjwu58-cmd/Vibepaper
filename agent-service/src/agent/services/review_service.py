"""RenderReview 持久化与质量路由；本层只提出重跑决策，不直接提交生成。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..domain.drama_schema import RenderReview as DramaRenderReview
from ..domain.quality_router import route_review
from ..models import RenderReview
from .session_service import session_service


class ReviewValidationError(ValueError):
    pass


def _as_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ReviewValidationError(f"{field} 必须是整数") from exc
    if parsed <= 0:
        raise ReviewValidationError(f"{field} 必须大于 0")
    return parsed


class ReviewService:
    def record(self, db: Session, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
        canvas_id = _as_int(body.get("canvasId") or body.get("canvas_id"), "canvasId")
        target_node_id = _as_int(body.get("targetNodeId") or body.get("target_node_id"), "targetNodeId")
        data = {
            "target_node_id": str(target_node_id),
            "target_kind": body.get("targetKind") or body.get("target_kind") or "clip",
            "scores": body.get("scores") or {},
            "failures": body.get("failures") or [],
            "recommended_action": body.get("recommendedAction") or body.get("recommended_action") or "accept",
            "evidence": body.get("evidence") or {},
            "retry_count": body.get("retryCount") or body.get("retry_count") or 0,
        }
        try:
            review = DramaRenderReview.model_validate(data)
        except Exception as exc:
            raise ReviewValidationError(f"质量审查参数无效: {exc}") from exc

        remaining_cost_cap = (
            body["remainingCostCap"] if "remainingCostCap" in body else body.get("remaining_cost_cap")
        )
        decision = route_review(
            review,
            remaining_cost_cap=remaining_cost_cap,
            extra_cost=int(body.get("extraCost") or body.get("extra_cost") or 0),
            thresholds=body.get("thresholds"),
        )
        action = decision["action"]
        status = {"accept": "accepted", "rerun_local": "needs_retry", "human_review": "needs_review"}.get(
            action, "blocked"
        )
        row = RenderReview(
            id=session_service.next_id(),
            canvas_id=canvas_id,
            user_id=user_id,
            target_node_id=target_node_id,
            target_kind=review.target_kind,
            scores=review.scores,
            failures=decision["failures"],
            recommended_action=action,
            evidence=review.evidence,
            retry_count=review.retry_count,
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return self.to_dict(row, decision)

    def list(self, db: Session, user_id: int, canvas_id: int, target_node_id: int | None = None) -> list[dict[str, Any]]:
        query = db.query(RenderReview).filter(RenderReview.user_id == user_id, RenderReview.canvas_id == canvas_id)
        if target_node_id is not None:
            query = query.filter(RenderReview.target_node_id == target_node_id)
        return [self.to_dict(row) for row in query.order_by(RenderReview.created_at.desc()).limit(200).all()]

    @staticmethod
    def to_dict(row: RenderReview, decision: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "reviewId": str(row.id),
            "canvasId": str(row.canvas_id),
            "targetNodeId": str(row.target_node_id),
            "targetKind": row.target_kind,
            "scores": row.scores or {},
            "failures": row.failures or [],
            "recommendedAction": row.recommended_action,
            "retryCount": int(row.retry_count or 0),
            "status": row.status,
            "evidence": row.evidence or {},
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }
        if decision is not None:
            # 前端据此创建一个新的高风险 action；服务端绝不在审查回调中直接提交生成。
            result["decision"] = decision
            result["requiresConfirmation"] = decision.get("action") == "rerun_local"
        return result


review_service = ReviewService()
