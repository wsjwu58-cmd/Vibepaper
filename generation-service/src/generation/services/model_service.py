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
    """种子模型目录（B-11）：文本/图片/视频/音频 + 合成/导演台；已有库时补齐缺失项。"""
    seeds = [
        ("qwen-max", "text", "通义千问 Max", "通用文本生成", "qwen", 12, {"prompt": ""}),
        ("deepseek-v4-pro", "text", "DeepSeek V4 Pro", "复杂推理与 Agent 编排（推荐）", "deepseek", 12, {"prompt": ""}),
        ("deepseek-v4-flash", "text", "DeepSeek V4 Flash", "高速对话与文案", "deepseek", 4, {"prompt": ""}),
        ("deepseek-chat", "text", "DeepSeek Chat", "旧版别名（兼容）", "deepseek", 8, {"prompt": ""}),
        ("gpt-4o-mini", "text", "GPT-4o mini", "轻量文本生成", "openai", 5, {"prompt": ""}),
        # 图片：优先账号有免费额度的 Seedream 5.0-lite
        ("doubao-seedream-5-0-260128", "image", "Seedream 5.0 Lite", "火山方舟文生图/图生图（免费额度·推荐）", "seedream", 8, {"resolution": "1920x1080", "size": "2K"}),
        ("doubao-seedream-4-0-250828", "image", "Seedream 4.0", "火山方舟文生图/图生图", "seedream", 12, {"resolution": "1024x1024", "size": "1K"}),
        ("doubao-seedream-4-5-251128", "image", "Seedream 4.5", "火山方舟文生图", "seedream", 12, {"resolution": "1024x1024", "size": "1K"}),
        ("seedream-4", "image", "Seedream 4", "Seedream 5.0 Lite 别名", "seedream", 8, {"resolution": "1920x1080", "size": "2K"}),
        ("flux-dev", "image", "FLUX.1 dev", "高质量文生图（本地 Mock 兜底）", "mock-image", 20, {"resolution": "1024x1024"}),
        ("sd3-medium", "image", "Stable Diffusion 3", "通用文生图（本地 Mock）", "mock-image", 15, {"resolution": "1024x1024"}),
        # 视频：需在方舟控制台开通 Seedance；失败时返回明确错误，不回退 Mock
        ("doubao-seedance-1-0-pro-250528", "video", "Seedance 1.0 Pro", "火山方舟视频（需控制台开通）", "seedance", 30, {"resolution": "1280x720", "duration": 5}),
        ("doubao-seedance-2-0-mini-260615", "video", "Seedance 2.0 Mini", "火山方舟视频（更省·需开通）", "seedance", 40, {"resolution": "1280x720", "duration": 5}),
        ("doubao-seedance-2-0-260128", "video", "Seedance 2.0", "火山方舟视频标准版（需开通）", "seedance", 80, {"resolution": "1280x720", "duration": 5}),
        ("seedance-1.0", "video", "Seedance 1.0 Pro", "Seedance 1.0 Pro 别名", "seedance", 30, {"resolution": "1280x720", "duration": 5}),
        ("wan-2.1", "video", "Wan 2.1", "文生视频（Seedance 1.0 Pro）", "seedance", 50, {"resolution": "1280x720"}),
        ("kling-2.0", "video", "可灵 2.0", "视频生成（本地 Mock）", "mock-video", 60, {"resolution": "1280x720"}),
        ("music-1.5", "audio", "Music 1.5", "音乐生成", "mock-audio", 10, {}),
        ("audio-1.0", "audio", "Audio 1.0", "通用音频生成", "mock-audio", 8, {}),
        ("compose-1.0", "compose", "视频合成", "多段视频按顺序拼接成片", "mock-compose", 15, {"operation": "compose"}),
        ("director-1.0", "director", "导演台", "导演台拍照渲染", "mock-director", 10, {}),
    ]
    existing = {m.name: m for m in db.query(ModelConfig).all()}
    created = False
    for name, mtype, display, desc, provider, price, defaults in seeds:
        if name in existing:
            m = existing[name]
            # 纠正历史 seed / 切换到更便宜的方舟模型
            if m.provider != provider and provider in {"deepseek", "qwen", "openai", "seedream", "seedance", "openai-text", "mock-image", "mock-video", "mock-audio", "mock-compose", "mock-director"}:
                # 仅在从 mock 升级到真实供应商，或 seedream/seedance/文本品牌纠正时改写
                if m.provider in {"mock", "mock-image", "mock-video", "volcengine-ark", "openai-text"} or provider in {"seedream", "seedance", "deepseek", "qwen", "openai"}:
                    m.provider = provider
                    m.display_name = display
                    m.description = desc
                    m.base_price = price
                    created = True
            # 文本品牌 / 别名展示信息同步
            if name in {"deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "qwen-max", "gpt-4o-mini", "seedream-4", "seedance-1.0"} and (
                m.display_name != display or m.provider != provider or m.base_price != price
            ):
                m.display_name = display
                m.description = desc
                m.base_price = price
                m.provider = provider
                created = True
            continue
        m = ModelConfig(id=model_service.next_id(), name=name, model_type=mtype, display_name=display,
                        description=desc, provider=provider, enabled=True, default_params=defaults,
                        base_price=price)
        db.add(m)
        db.flush()
        db.add(PricingRule(id=model_service.next_id(), model_id=m.id,
                           rule_key="resolution", rule_value="1920x1080", points=price + 10))
        db.add(PricingRule(id=model_service.next_id(), model_id=m.id,
                           rule_key="resolution", rule_value="3840x2160", points=price + 25))
        created = True
    if created:
        db.commit()
