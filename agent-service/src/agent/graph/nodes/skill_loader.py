"""skill_loader：注入 Paper 基线 + Skill 目录摘要（不再关键词预载）。"""

from __future__ import annotations

from ...agent.persona import PAPER_AGENT_INSTRUCTIONS, PAPER_AGENT_SKILL_NAME
from ...core.db import SessionLocal
from ...domain.skill_catalog import catalog_summary_for_prompt
from ...models import AgentSession, Skill
from ..state import AgentState


def skill_loader_node(state: AgentState) -> dict:
    db = SessionLocal()
    instructions = f"{PAPER_AGENT_INSTRUCTIONS}\n\n{catalog_summary_for_prompt()}"
    skill_name = PAPER_AGENT_SKILL_NAME
    try:
        session = db.get(AgentSession, state["session_id"])
        if session and session.skill_id:
            skill = db.get(Skill, session.skill_id)
            if skill and skill.instructions:
                instructions = f"{skill.instructions}\n\n{catalog_summary_for_prompt(12)}"
                skill_name = skill.name
    finally:
        db.close()

    return {
        "skill_instructions": instructions,
        "skill_name": skill_name,
        "events": [{"type": "skill_loaded", "skill": skill_name}],
    }
