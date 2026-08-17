"""模型目录与定价（B-11 / B-41 / B-43）。"""

import itertools
import time

from sqlalchemy.orm import Session

from ..models import ModelConfig, PricingRule

_id_seq = itertools.count(1)
_SNOWFLAKE_EPOCH_MS = 1735689600000


def next_id() -> int:
    """对齐 Snowflake 时间窗，避免左移导致 bigint 溢出。"""
    ts = max(0, int(time.time() * 1000) - _SNOWFLAKE_EPOCH_MS)
    return (ts << 22) | (next(_id_seq) & 0x3FFFFF)


class ModelService:
    def list_models(self, db: Session, model_type: str | None = None, include_disabled: bool = False):
        q = db.query(ModelConfig)
        if model_type:
            q = q.filter(ModelConfig.model_type == model_type)
        if not include_disabled:
            q = q.filter(ModelConfig.enabled == True)  # noqa: E712
        models = q.order_by(ModelConfig.id).all()
        return [self.to_dict(db, m) for m in models]

    def to_dict(self, db: Session, m: ModelConfig) -> dict:
        rules = db.query(PricingRule).filter(PricingRule.model_id == m.id).all()
        return {
            "id": m.id,
            "name": m.name,
            "modelType": m.model_type,
            "displayName": m.display_name,
            "description": m.description,
            "provider": m.provider,
            "baseUrl": m.base_url,
            "enabled": m.enabled,
            "defaultParams": m.default_params or {},
            "basePrice": m.base_price,
            "pricingRules": [{"ruleKey": r.rule_key, "ruleValue": r.rule_value, "points": r.points} for r in rules],
        }

    def create(self, db: Session, body: dict) -> ModelConfig:
        m = ModelConfig(
            id=body.get("id") or self.next_id(),
            name=body["name"],
            model_type=body.get("modelType", "text"),
            display_name=body.get("displayName"),
            description=body.get("description"),
            provider=body.get("provider", "mock"),
            base_url=body.get("baseUrl"),
            api_key_ref=body.get("apiKeyRef"),
            enabled=body.get("enabled", True),
            default_params=body.get("defaultParams") or {},
            base_price=body.get("basePrice", 10),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m

    def update(self, db: Session, model_id: int, body: dict) -> ModelConfig | None:
        m = db.get(ModelConfig, model_id)
        if not m:
            return None
        for field in ("displayName", "description", "provider", "baseUrl", "apiKeyRef", "defaultParams", "basePrice"):
            if field in body:
                setattr(m, field, body[field])
        if "enabled" in body:
            m.enabled = bool(body["enabled"])
        if "name" in body:
            m.name = body["name"]
        if "modelType" in body:
            m.model_type = body["modelType"]
        db.commit()
        db.refresh(m)
        return m

    def delete(self, db: Session, model_id: int) -> bool:
        m = db.get(ModelConfig, model_id)
        if not m:
            return False
        db.query(PricingRule).filter(PricingRule.model_id == model_id).delete()
        db.delete(m)
        db.commit()
        return True

    def update_pricing(self, db: Session, model_id: int, rules: list[dict]) -> ModelConfig | None:
        m = db.get(ModelConfig, model_id)
        if not m:
            return None
        if "basePrice" in rules[0] if rules else False:
            m.base_price = int(rules[0]["basePrice"])
        db.query(PricingRule).filter(PricingRule.model_id == model_id).delete()
        for r in rules:
            if "ruleKey" in r:
                db.add(PricingRule(id=self.next_id(), model_id=model_id,
                                   rule_key=r["ruleKey"], rule_value=str(r["ruleValue"]),
                                   points=int(r["points"])))
        db.commit()
        db.refresh(m)
        return m

    @staticmethod
    def next_id() -> int:
        return next_id()



model_service = ModelService()


def seed_models(db: Session):
    """种子模型目录：文本仅 Agnes 2.5 Flash；图像/视频默认 Agnes。"""
    # (name, type, display, desc, provider, price, defaults, enabled)
    seeds = [
        # 文本：仅 Agnes 2.5 Flash
        ("agnes-2.5-flash", "text", "Agnes 2.5 Flash", "Agnes 对话/Agent/画布文本（推荐）", "agnes-text", 8, {"prompt": ""}, True),
        # 图片：Agnes Image 2.1 Flash
        ("agnes-image-2.1-flash", "image", "Agnes Image 2.1 Flash", "Agnes 文生图/图生图/多图合成（推荐）", "agnes-image", 8, {"resolution": "1920x1080", "size": "2K", "ratio": "16:9"}, True),
        ("seedream-4", "image", "Agnes Image 2.1 Flash", "兼容别名 → Agnes Image", "agnes-image", 8, {"resolution": "1920x1080", "size": "2K", "ratio": "16:9"}, False),
        ("doubao-seedream-5-0-260128", "image", "Agnes Image 2.1 Flash", "兼容别名 → Agnes Image", "agnes-image", 8, {"resolution": "1920x1080", "size": "2K"}, False),
        ("doubao-seedream-4-0-250828", "image", "Seedream 4.0", "已停用（改用 Agnes）", "agnes-image", 12, {"resolution": "1024x1024", "size": "1K"}, False),
        ("doubao-seedream-4-5-251128", "image", "Seedream 4.5", "已停用（改用 Agnes）", "agnes-image", 12, {"resolution": "1024x1024", "size": "1K"}, False),
        ("flux-dev", "image", "FLUX.1 dev", "本地 Mock（已停用）", "mock-image", 20, {"resolution": "1024x1024"}, False),
        ("sd3-medium", "image", "Stable Diffusion 3", "本地 Mock（已停用）", "mock-image", 15, {"resolution": "1024x1024"}, False),
        # 视频：Agnes Video V2.0
        ("agnes-video-v2.0", "video", "Agnes Video V2.0", "Agnes 文生视频/图生视频/关键帧（推荐）", "agnes-video", 35, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, True),
        ("seedance-1.0", "video", "Agnes Video V2.0", "兼容别名 → Agnes Video", "agnes-video", 35, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("wan-2.1", "video", "Agnes Video V2.0", "兼容别名 → Agnes Video", "agnes-video", 35, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("doubao-seedance-1-5-pro-251215", "video", "Agnes Video V2.0", "兼容别名 → Agnes Video", "agnes-video", 35, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("doubao-seedance-1-0-pro-250528", "video", "Seedance 1.0 Pro", "已停用（改用 Agnes）", "agnes-video", 30, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("doubao-seedance-2-0-mini-260615", "video", "Seedance 2.0 Mini", "已停用（改用 Agnes）", "agnes-video", 40, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("doubao-seedance-2-0-260128", "video", "Seedance 2.0", "已停用（改用 Agnes）", "agnes-video", 80, {"resolution": "1152x768", "duration": 5, "ratio": "16:9"}, False),
        ("kling-2.0", "video", "可灵 2.0", "本地 Mock（已停用）", "mock-video", 60, {"resolution": "1280x720"}, False),
        # 音频：豆包语音合成（需 VIBEPAPER_SPEECH_*）；旧 Mock 停用
        ("doubao-tts", "audio", "豆包语音合成", "旁白/对白 TTS（火山语音·免费额度）", "doubao-tts", 8, {"voice": "zh_female_tianmeixiaoyuan_moon_bigtts", "speed": 1.0}, True),
        ("doubao-tts-2", "audio", "豆包语音合成 2.0", "语音合成 2.0（火山语音）", "doubao-tts", 8, {"voice": "zh_female_tianmeixiaoyuan_moon_bigtts", "speed": 1.0}, True),
        ("music-1.5", "audio", "Music 1.5", "本地 Mock（已停用）", "mock-audio", 10, {}, False),
        ("audio-1.0", "audio", "Audio 1.0", "本地 Mock（已停用）", "mock-audio", 8, {}, False),
        ("compose-1.0", "compose", "视频合成", "多段视频按顺序拼接成片（本地 FFmpeg）", "mock-compose", 15, {"operation": "compose"}, True),
        ("director-1.0", "director", "导演台", "导演台拍照渲染（本地）", "mock-director", 10, {}, True),
    ]
    existing = {m.name: m for m in db.query(ModelConfig).all()}
    created = False
    for name, mtype, display, desc, provider, price, defaults, enabled in seeds:
        if name in existing:
            m = existing[name]
            dirty = False
            if m.provider != provider:
                m.provider = provider
                dirty = True
            if m.display_name != display or m.description != desc or m.base_price != price:
                m.display_name = display
                m.description = desc
                m.base_price = price
                dirty = True
            if m.enabled != enabled:
                m.enabled = enabled
                dirty = True
            if defaults and m.default_params != defaults:
                m.default_params = defaults
                dirty = True
            if dirty:
                created = True
            continue
        m = ModelConfig(
            id=model_service.next_id(),
            name=name,
            model_type=mtype,
            display_name=display,
            description=desc,
            provider=provider,
            enabled=enabled,
            default_params=defaults,
            base_price=price,
        )
        db.add(m)
        db.flush()
        db.add(PricingRule(id=model_service.next_id(), model_id=m.id,
                           rule_key="resolution", rule_value="1920x1080", points=price + 10))
        db.add(PricingRule(id=model_service.next_id(), model_id=m.id,
                           rule_key="resolution", rule_value="3840x2160", points=price + 25))
        created = True
    for m in list(db.query(ModelConfig).filter(ModelConfig.model_type == "text").all()):
        if m.name != "agnes-2.5-flash":
            db.query(PricingRule).filter(PricingRule.model_id == m.id).delete()
            db.delete(m)
            created = True
    if created:
        db.commit()
