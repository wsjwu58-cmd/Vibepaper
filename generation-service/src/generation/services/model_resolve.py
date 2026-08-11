"""将 modality 别名（text/image/…）解析为具体 ModelConfig。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import ModelConfig

MODALITY_ALIASES = frozenset({"text", "image", "video", "audio", "compose", "director"})
_MOCK_PROVIDERS = frozenset({
    "mock", "mock-text", "mock-image", "mock-video", "mock-audio", "mock-compose", "mock-director",
})


def _preferred_name(modality: str) -> str | None:
    mapping = {
        "text": (settings.llm_model or "deepseek-v4-pro").strip() or "deepseek-v4-pro",
        "image": (settings.ark_image_model or "doubao-seedream-5-0-260128").strip(),
        "video": (settings.ark_video_model or "doubao-seedance-1-0-pro-250528").strip(),
        "audio": "audio-1.0",
        "compose": "compose-1.0",
        "director": "director-1.0",
    }
    return mapping.get(modality)


def resolve_model_config(db: Session, model_type: str) -> ModelConfig | None:
    """按模型名精确匹配；若是 modality 别名则选推荐/非 mock 的启用模型。"""
    name = (model_type or "").strip()
    if not name:
        return None

    exact = db.query(ModelConfig).filter(ModelConfig.name == name).first()
    if exact:
        return exact

    modality = name.lower()
    if modality not in MODALITY_ALIASES:
        return None

    preferred = _preferred_name(modality)
    if preferred:
        hit = (
            db.query(ModelConfig)
            .filter(ModelConfig.name == preferred, ModelConfig.enabled.is_(True))
            .first()
        )
        if hit:
            return hit

    candidates = (
        db.query(ModelConfig)
        .filter(ModelConfig.model_type == modality, ModelConfig.enabled.is_(True))
        .order_by(ModelConfig.id)
        .all()
    )
    for m in candidates:
        if (m.provider or "").lower() not in _MOCK_PROVIDERS:
            return m
    return candidates[0] if candidates else None
