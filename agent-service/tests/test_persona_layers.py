"""人格三层 + 语义边界 + 铁路火车头契约。"""

from agent.agent.persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS


def test_agent_persona_has_three_layers_and_reply_morphologies():
    assert "你是 DD" in AGENT_PERSONA
    assert "性格层" in AGENT_PERSONA
    assert "原则层" in AGENT_PERSONA
    assert "规则层" in AGENT_PERSONA
    assert "取舍优先级" in AGENT_PERSONA
    assert "confirmedAction" in AGENT_PERSONA or "确认卡" in AGENT_PERSONA
    assert "分工" in AGENT_PERSONA or "铁路" in AGENT_PERSONA
    for morph in ("动作型", "决策型", "建议型", "反对型"):
        assert morph in AGENT_PERSONA
    assert "不背" in AGENT_PERSONA or "不背稿" in AGENT_PERSONA
    assert "缺了才查" in AGENT_PERSONA or "缺了才补" in AGENT_PERSONA
    assert "jobId" in AGENT_PERSONA or "task_id" in AGENT_PERSONA
    assert "不报名字" in AGENT_PERSONA or "不自我介绍" in AGENT_PERSONA
    assert "好商量" in AGENT_PERSONA or "暖一点" in AGENT_PERSONA


def test_persona_semantic_boundaries():
    assert "动作 vs 讨论" in AGENT_PERSONA or "讨论" in AGENT_PERSONA
    assert "六格漫画" in AGENT_PERSONA
    assert "关键词" in AGENT_PERSONA
    assert "Creative Planner" in AGENT_PERSONA or "创意规划" in AGENT_PERSONA


def test_paper_instructions_align_with_persona_layers():
    assert "你是 DD" in PAPER_AGENT_INSTRUCTIONS
    assert "交互三层" in PAPER_AGENT_INSTRUCTIONS
    assert "动作型" in PAPER_AGENT_INSTRUCTIONS
    assert "决策型" in PAPER_AGENT_INSTRUCTIONS
    assert "取舍优先级" in PAPER_AGENT_INSTRUCTIONS or "confirmedAction" in PAPER_AGENT_INSTRUCTIONS
    assert "产物边界" in PAPER_AGENT_INSTRUCTIONS
    assert "queued" in PAPER_AGENT_INSTRUCTIONS
    assert "不报名字" in PAPER_AGENT_INSTRUCTIONS or "自我介绍" in PAPER_AGENT_INSTRUCTIONS
