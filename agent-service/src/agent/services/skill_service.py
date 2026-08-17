"""Skill 系统：默认 Skill 从 default_skills_seed 入库；运行时只读数据库。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..agent.persona import PAPER_AGENT_INSTRUCTIONS, PAPER_AGENT_SKILL_NAME
from ..domain.default_skills_seed import DEFAULT_SKILLS_SEED
from ..models import Skill
from .session_service import session_service

SYSTEM_OWNER_ID = 0


def skill_to_dict(s: Skill) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "instructions": s.instructions,
        "source": s.source,
        "category": getattr(s, "category", None) or "general",
        "version": s.version,
        "enabled": bool(s.enabled),
        "ownerId": s.owner_id,
        "createdAt": s.created_at.isoformat() if s.created_at else None,
        "updatedAt": s.updated_at.isoformat() if s.updated_at else None,
    }


class SkillService:
    def list(
        self,
        db: Session,
        user_id: int,
        keyword: str | None = None,
        *,
        category: str | None = None,
        include_disabled: bool = False,
        mine_only: bool = False,
    ):
        q = db.query(Skill)
        if mine_only:
            q = q.filter(Skill.owner_id == user_id, Skill.source != "builtin")
        else:
            q = q.filter(or_(Skill.owner_id == user_id, Skill.owner_id == SYSTEM_OWNER_ID))
        if not include_disabled:
            q = q.filter(Skill.enabled == True)  # noqa: E712
        if keyword:
            like = f"%{keyword}%"
            q = q.filter(or_(Skill.name.ilike(like), Skill.description.ilike(like)))
        if category and category not in ("all", "全部", "favorite", "收藏"):
            if category in ("mine", "我的"):
                q = q.filter(Skill.owner_id == user_id, Skill.source != "builtin")
            else:
                q = q.filter(Skill.category == category)
        # 内置按名称稳定排序，用户 Skill 靠前
        return q.order_by(Skill.owner_id.desc(), Skill.name.asc()).all()

    def ensure_paper_agent(self, db: Session, user_id: int | None = None) -> Skill:
        skill = (
            db.query(Skill)
            .filter(Skill.name == PAPER_AGENT_SKILL_NAME, Skill.source == "builtin")
            .first()
        )
        if skill is None:
            skill = Skill(
                id=session_service.next_id(),
                owner_id=SYSTEM_OWNER_ID,
                name=PAPER_AGENT_SKILL_NAME,
                description="Paper Agent：梳理画布 / 品牌文案 / 延展方向（性格·原则·规则三层）",
                instructions=PAPER_AGENT_INSTRUCTIONS,
                source="builtin",
                category="general",
                version=1,
                enabled=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(skill)
            db.commit()
            db.refresh(skill)
        elif skill.instructions != PAPER_AGENT_INSTRUCTIONS:
            skill.instructions = PAPER_AGENT_INSTRUCTIONS
            skill.version += 1
            db.commit()
            db.refresh(skill)
        return skill

    def ensure_builtin_skills(self, db: Session) -> int:
        """将 DEFAULT_SKILLS_SEED 写入 skills 表（幂等 upsert）。不读 md 文件。"""
        self.ensure_paper_agent(db)
        upserted = 0
        for item in DEFAULT_SKILLS_SEED:
            name = item["name"]
            description = item.get("description") or name
            instructions = item.get("instructions") or ""
            if not instructions.startswith("#"):
                instructions = f"# {name}\n\n{instructions}"
            category = item.get("category") or "general"
            existing = (
                db.query(Skill)
                .filter(Skill.name == name, Skill.source == "builtin")
                .first()
            )
            if existing is None:
                db.add(Skill(
                    id=session_service.next_id(),
                    owner_id=SYSTEM_OWNER_ID,
                    name=name,
                    description=description,
                    instructions=instructions,
                    source="builtin",
                    category=category,
                    version=1,
                    enabled=True,
                    created_at=datetime.now(timezone.utc),
                ))
                upserted += 1
            else:
                changed = False
                if existing.description != description:
                    existing.description = description
                    changed = True
                if existing.instructions != instructions:
                    existing.instructions = instructions
                    existing.version += 1
                    changed = True
                if getattr(existing, "category", None) != category:
                    existing.category = category
                    changed = True
                if changed:
                    existing.updated_at = datetime.now(timezone.utc)
                    upserted += 1
        if upserted:
            db.commit()
        return upserted

    def presets(self, db: Session, user_id: int):
        self.ensure_builtin_skills(db)
        return self.list(db, user_id, include_disabled=False)

    def create(
        self,
        db: Session,
        user_id: int,
        name: str,
        description: str | None,
        instructions: str,
        source: str = "manual",
        category: str = "general",
    ) -> Skill:
        if not name or not instructions:
            raise ValueError("名称与指令必填")
        skill = Skill(
            id=session_service.next_id(),
            owner_id=user_id,
            name=name,
            description=description,
            instructions=instructions,
            source=source,
            category=category or "general",
            version=1,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill

    def from_conversation(self, db: Session, user_id: int, session_id: int, name: str | None) -> Skill:
        from ..core.config import settings
        from ..models import AgentMessage

        messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.id.asc())
            .limit(40)
            .all()
        )
        user_msgs = [m for m in messages if m.role == "user"][-5:]
        transcript = "\n".join(f"{m.role}: {(m.content or '')[:200]}" for m in messages[-12:])
        summary = "；".join((m.content or "")[:80] for m in user_msgs) or "基于对话生成"
        instructions = f"基于以下创作需求执行：\n{summary}"
        description = "由对话自动生成"
        if settings.llm_api_key and transcript:
            try:
                import json
                import re

                import httpx

                base = settings.normalized_llm_base_url()
                resp = httpx.post(
                    f"{base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "将对话总结为一个可复用 Skill。输出 JSON："
                                           "{\"name\":\"\",\"description\":\"\",\"instructions\":\"\"}",
                            },
                            {"role": "user", "content": transcript},
                        ],
                        "temperature": 0.2,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"] or "{}"
                match = re.search(r"\{.*\}", raw, re.S)
                data = json.loads(match.group(0) if match else raw)
                name = name or data.get("name") or name
                description = data.get("description") or description
                instructions = data.get("instructions") or instructions
            except Exception:
                pass
        skill_name = name or f"对话总结 {datetime.now(timezone.utc).strftime('%m%d%H%M')}"
        return self.create(db, user_id, skill_name, description, instructions, "from_conversation")

    def upload(self, db: Session, user_id: int, filename: str, content: bytes) -> Skill:
        if len(content) > 512 * 1024:
            raise ValueError("文件超过 512KB")
        text = content.decode("utf-8", errors="replace")
        if not filename.endswith(".md") and not filename.endswith(".markdown"):
            raise ValueError("仅支持 .md 文件")
        name = filename.rsplit(".", 1)[0][:64] or "上传 Skill"
        return self.create(db, user_id, name, "上传的 Skill 文件", text, "upload")

    def get(self, db: Session, skill_id: int, user_id: int) -> Skill | None:
        skill = db.get(Skill, skill_id)
        if not skill:
            return None
        if skill.owner_id == user_id or skill.source == "builtin" or skill.owner_id == SYSTEM_OWNER_ID:
            return skill
        return None

    def update(
        self,
        db: Session,
        skill_id: int,
        user_id: int,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        enabled: bool | None = None,
        category: str | None = None,
    ) -> Skill | None:
        skill = self.get(db, skill_id, user_id)
        if not skill:
            return None
        is_builtin = skill.source == "builtin" or skill.owner_id == SYSTEM_OWNER_ID
        if is_builtin and (name is not None or description is not None or instructions is not None):
            raise ValueError("内置 Skill 不可编辑内容")
        if not is_builtin:
            if name:
                skill.name = name
            if description is not None:
                skill.description = description
            if instructions:
                skill.instructions = instructions
                skill.version += 1
            if category is not None:
                skill.category = category
        if enabled is not None and not is_builtin:
            skill.enabled = enabled
        skill.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(skill)
        return skill

    def delete(self, db: Session, skill_id: int, user_id: int) -> bool:
        skill = self.get(db, skill_id, user_id)
        if not skill:
            return False
        if skill.source == "builtin" or skill.owner_id == SYSTEM_OWNER_ID:
            raise ValueError("内置 Skill 不可删除")
        db.delete(skill)
        db.commit()
        return True


skill_service = SkillService()
