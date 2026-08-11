"""skill_loader：按需加载复合 Skill，用完即丢。"""

from __future__ import annotations

from ...agent.persona import PAPER_AGENT_INSTRUCTIONS, PAPER_AGENT_SKILL_NAME, detect_composite_skill
from ...core.db import SessionLocal
from ...models import AgentSession, Skill
from ...services.telemetry import skill_loaded
from ...tools.registry import TOOLS
from ..state import AgentState


def skill_loader_node(state: AgentState) -> dict:
    db = SessionLocal()
    instructions = PAPER_AGENT_INSTRUCTIONS
    skill_name = PAPER_AGENT_SKILL_NAME
    try:
        session = db.get(AgentSession, state["session_id"])
        if session and session.skill_id:
            skill = db.get(Skill, session.skill_id)
            if skill and skill.instructions:
                instructions = skill.instructions
                skill_name = skill.name
        # 复合操作按需加载
        composite = detect_composite_skill(state["user_content"])
        if composite and "load_skill" in TOOLS:
            loaded = TOOLS["load_skill"].fn(
                canvas_id=state.get("canvas_id") or 0,
                user_id=state["user_id"],
                skill_key=composite,
            )
            extra = loaded.get("instructions") or ""
            if extra:
                instructions = f"{instructions}\n\n## 按需 Skill: {composite}\n{extra}"
                skill_name = f"{skill_name}+{composite}"
                skill_loaded(state["session_id"], composite)
    finally:
        db.close()

    events = list(state.get("events") or [])
    events.append({"type": "skill_loaded", "skill": skill_name})
    return {
        "skill_instructions": instructions,
        "skill_name": skill_name,
        "events": events,
    }
