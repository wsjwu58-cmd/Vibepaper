"""提交生成时：把 modality 别名解析为具体模型名。"""

from __future__ import annotations

from ..core.config import settings
from .video_task import DEFAULT_VIDEO_MODEL

MODALITY_ALIASES = frozenset({"text", "image", "video", "audio", "compose", "director"})
TEXT_MODEL_ALIASES = {
    "deepseek-v4-pro": "agnes-2.5-flash",
    "deepseek-v4-flash": "agnes-2.5-flash",
    "deepseek-chat": "agnes-2.5-flash",
    "qwen-max": "agnes-2.5-flash",
    "gpt-4o-mini": "agnes-2.5-flash",
}

_DEFAULTS = {
    "text": lambda: (settings.llm_model or "agnes-2.5-flash").strip() or "agnes-2.5-flash",
    "image": lambda: "agnes-image-2.5-flash",
    "video": lambda: DEFAULT_VIDEO_MODEL,
    "audio": lambda: "doubao-tts",
    "compose": lambda: "compose-1.0",
    "director": lambda: "director-1.0",
}


def resolve_submit_model(
    model_type: str | None,
    *,
    model_params: dict | None = None,
    node_model_ref: str | None = None,
) -> str:
    """优先显式模型名，其次节点 modelRef，最后按 modality 默认。"""
    params = model_params or {}
    # 合成/导演台按 operation 强制路由，避免被 video 默认模型（Seedance）抢走
    op = str(params.get("operation") or "").lower()
    if op in {"compose", "合成"} or str(model_type or "").lower() in {"compose", "compose-1.0"}:
        return "compose-1.0"
    if op in {"director", "导演台"} or str(model_type or "").lower() in {"director", "director-1.0"}:
        return "director-1.0"

    for key in ("model", "modelRef", "model_name", "modelName"):
        raw = params.get(key)
        if raw is None:
            continue
        name = str(raw).strip()
        if name and name.lower() not in MODALITY_ALIASES:
            return TEXT_MODEL_ALIASES.get(name.lower(), name)

    if node_model_ref:
        ref = str(node_model_ref).strip()
        if ref and ref.lower() not in MODALITY_ALIASES:
            # 合成节点上可能残留 seedance modelRef，不能跟着走
            if str(model_type or "").lower() == "compose":
                return "compose-1.0"
            return TEXT_MODEL_ALIASES.get(ref.lower(), ref)

    mt = (model_type or "text").strip()
    if not mt:
        mt = "text"
    if mt.lower() in MODALITY_ALIASES:
        factory = _DEFAULTS[mt.lower()]
        return factory()
    return TEXT_MODEL_ALIASES.get(mt.lower(), mt)
