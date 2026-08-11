"""Skill 系统（P1｜F-16/B-28）。"""

import re
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..agent.persona import PAPER_AGENT_INSTRUCTIONS, PAPER_AGENT_SKILL_NAME
from ..models import Skill
from .session_service import session_service


PRESET_SKILLS = [
    ("短片编剧", "将一句话创意拆解为剧本、角色与分镜", "1. 将用户创意扩写为三幕结构剧本\n2. 拆解关键场景\n3. 为每个场景生成提示词"),
    ("品牌海报", "生成符合品牌调性的海报方案", "1. 提取品牌关键词\n2. 确定视觉风格\n3. 生成海报构图与文案"),
    ("概念设计", "角色/场景概念设定图", "1. 明确设计目标\n2. 列出关键视觉元素\n3. 生成多角度设定图"),
]

# 系统内置：owner_id=0，不对普通用户开放编辑
SYSTEM_OWNER_ID = 0


class SkillService:
    def list(self, db: Session, user_id: int, keyword: str | None = None):
        q = db.query(Skill).filter(
            or_(Skill.owner_id == user_id, Skill.owner_id == SYSTEM_OWNER_ID),
            Skill.enabled == True,  # noqa: E712
        )
        if keyword:
            q = q.filter(or_(Skill.name.ilike(f"%{keyword}%"), Skill.description.ilike(f"%{keyword}%")))
        return q.order_by(Skill.created_at.desc()).all()

    def ensure_paper_agent(self, db: Session, user_id: int | None = None) -> Skill:
        """确保内置 paper-agent-default Skill 存在。"""
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
                description="Paper Agent：梳理画布 / 品牌文案 / 延展方向",
                instructions=PAPER_AGENT_INSTRUCTIONS,
                source="builtin",
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

    def presets(self, db: Session, user_id: int):
        self.ensure_paper_agent(db)
        if db.query(Skill).filter(Skill.owner_id == user_id, Skill.source == "preset").count() == 0:
            for name, desc, instructions in PRESET_SKILLS:
                db.add(Skill(id=session_service.next_id(), owner_id=user_id, name=name, description=desc,
                             instructions=instructions, source="preset", version=1, enabled=True,
                             created_at=datetime.now(timezone.utc)))
            db.commit()
        return self.list(db, user_id)

    def create(self, db: Session, user_id: int, name: str, description: str | None,
               instructions: str, source: str = "manual") -> Skill:
        if not name or not instructions:
            raise ValueError("名称与指令必填")
        skill = Skill(id=session_service.next_id(), owner_id=user_id, name=name, description=description,
                      instructions=instructions, source=source, version=1, enabled=True,
                      created_at=datetime.now(timezone.utc))
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill

    def from_conversation(self, db: Session, user_id: int, session_id: int, name: str | None) -> Skill:
        """从当前对话生成 Skill；配置 LLM 时用模型总结，否则回退拼接。"""
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

    def update(self, db: Session, skill_id: int, user_id: int, name: str | None = None,
               description: str | None = None, instructions: str | None = None) -> Skill | None:
        skill = self.get(db, skill_id, user_id)
        if not skill:
            return None
        if skill.source == "builtin" or skill.owner_id == SYSTEM_OWNER_ID:
            raise ValueError("内置 Skill 不可编辑")
        if name:
            skill.name = name
        if description is not None:
            skill.description = description
        if instructions:
            skill.instructions = instructions
            skill.version += 1
        skill.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(skill)
        return skill

    def delete(self, db: Session, skill_id: int, user_id: int) -> bool:
        skill = self.get(db, skill_id, user_id)
        if not skill:
            return False
        db.delete(skill)
        db.commit()
        return True


skill_service = SkillService()
