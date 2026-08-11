"""提交生成时：把 modality 别名解析为具体模型名。"""

from __future__ import annotations

from ..core.config import settings
from .video_task import DEFAULT_VIDEO_MODEL

MODALITY_ALIASES = frozenset({"text", "image", "video", "audio", "compose", "director"})

_DEFAULTS = {
    "text": lambda: (settings.llm_model or "deepseek-v4-pro").strip() or "deepseek-v4-pro",
    "image": lambda: "doubao-seedream-5-0-260128",
    "video": lambda: DEFAULT_VIDEO_MODEL,
    "audio": lambda: "audio-1.0",
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
            return name

    if node_model_ref:
        ref = str(node_model_ref).strip()
        if ref and ref.lower() not in MODALITY_ALIASES:
            # 合成节点上可能残留 seedance modelRef，不能跟着走
            if str(model_type or "").lower() == "compose":
                return "compose-1.0"
            return ref

    mt = (model_type or "text").strip()
    if not mt:
        mt = "text"
    if mt.lower() in MODALITY_ALIASES:
        factory = _DEFAULTS[mt.lower()]
        return factory()
    return mt
