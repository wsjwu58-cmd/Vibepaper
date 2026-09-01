"""将 modality 别名（text/image/…）解析为具体 ModelConfig。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import ModelConfig

MODALITY_ALIASES = frozenset({"text", "image", "video", "audio", "compose", "director"})
TEXT_MODEL_ALIASES = {
    "deepseek-v4-pro": "agnes-2.5-flash",
    "deepseek-v4-flash": "agnes-2.5-flash",
    "deepseek-chat": "agnes-2.5-flash",
    "qwen-max": "agnes-2.5-flash",
    "gpt-4o-mini": "agnes-2.5-flash",
}
_MOCK_PROVIDERS = frozenset({
    "mock", "mock-text", "mock-image", "mock-video", "mock-audio", "mock-compose", "mock-director",
})


def _preferred_name(modality: str) -> str | None:
    speech_configured = bool((settings.speech_app_id or "").strip() and (settings.speech_token or "").strip())
    mapping = {
        "text": (settings.llm_model or "agnes-2.5-flash").strip() or "agnes-2.5-flash",
        "image": (settings.agnes_image_model or "agnes-image-2.5-flash").strip(),
        "video": (settings.agnes_video_model or "agnes-video-2.5-flash").strip(),
        "audio": "doubao-tts" if speech_configured else "local-sapi-tts" if settings.environment.lower() == "development" else "doubao-tts",
        "compose": "compose-1.0",
        "director": "director-1.0",
    }
    return mapping.get(modality)


def resolve_model_config(db: Session, model_type: str) -> ModelConfig | None:
    """按模型名精确匹配；若是 modality 别名则选推荐/非 mock 的启用模型。"""
    name = (model_type or "").strip()
    if not name:
        return None
    name = TEXT_MODEL_ALIASES.get(name.lower(), name)

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
