"""用户回复 A/B/C 时须对照上轮 next_actions 解析。"""

from agent.domain.llm_prompt import (
    build_user_prompt,
    last_offered_options,
    resolve_option_choice,
    serialize_recent_message,
)


def test_serialize_recent_message_keeps_next_actions():
    item = serialize_recent_message(
        role="assistant",
        content="想要哪种风格基调？",
        meta={
            "nextActions": [
                "A. 卡通喜剧风（汤姆杰瑞式）",
                "B. 拟人剧情风（有人设和对白）",
                "C. 动物写实+旁白叙事",
            ],
        },
    )
    assert item["content"].startswith("想要哪种")
    assert item["next_actions"][0].startswith("A.")


def test_resolve_letter_a_against_next_actions():
    recent = [
        {
            "role": "user",
            "content": "生成猫抓老鼠的短剧",
        },
        {
            "role": "assistant",
            "content": "想要哪种风格基调？这决定了后续所有创意方向",
            "next_actions": [
                "A. 卡通喜剧风（汤姆杰瑞式）",
                "B. 拟人剧情风（有人设和对白）",
                "C. 动物写实+旁白叙事",
            ],
        },
    ]
    assert last_offered_options(recent)[0].startswith("A.")
    resolved, matched = resolve_option_choice("A", recent)
    assert matched and "卡通喜剧风" in matched
    assert "选择：" in resolved
    assert "卡通喜剧风" in resolved


def test_choice_continue_forces_execution_intent():
    """选 A 后不得掉进 discussion；应展开并标记执行。"""
    from agent.domain.plan_models import IntentResult
    from agent.graph.nodes.orchestration_nodes import classify_intent_node

    recent = [
        {"role": "user", "content": "生成猫抓老鼠的短剧"},
        {
            "role": "assistant",
            "content": "想要哪种风格基调？",
            "next_actions": [
                "A. 卡通喜剧风（汤姆杰瑞式）",
                "B. 拟人剧情风",
            ],
        },
        {"role": "user", "content": "A"},
    ]

    def fake_hybrid(content, **kwargs):
        assert "卡通喜剧风" in content or "选择：" in content
        assert "create_nodes" in content or "落节点" in content
        return IntentResult(
            name="discussion",
            confidence=0.9,
            wants_execution=False,
            reasons=["model wrongly said discuss"],
        )

    import agent.graph.nodes.orchestration_nodes as orch

    old = orch.classify_intent_hybrid
    orch.classify_intent_hybrid = fake_hybrid
    try:
        out = classify_intent_node({
            "user_content": "A",
            "recent_messages": recent,
            "session_id": 1,
            "user_id": 1,
        })
    finally:
        orch.classify_intent_hybrid = old

    assert out["intent"]["wants_execution"] is True
    assert out["intent"]["name"] == "workflow_orchestration"
    assert "选择：" in (out.get("user_content") or "")
    assert "猫抓老鼠" in (out.get("user_content") or "")


def test_prep_only_finish_upgraded_to_act():
    from agent.graph.nodes.react_agent import react_agent_node

    # monkeypatch LLM to return finish + only load_skill
    import agent.graph.nodes.react_agent as ra

    def fake_llm(**kwargs):
        return {
            "thinking": "先加载 skill",
            "decision": "finish",
            "reply": "先落项目简报节点",
            "actions": [{"tool": "load_skill", "params": {"skill_key": "vertical-short-drama"}, "summary": "加载"}],
            "next_actions": [],
        }

    old = ra._call_react_llm
    old_fb = ra._structured_workflow_fallback
    ra._call_react_llm = fake_llm
    ra._structured_workflow_fallback = lambda state: None
    try:
        out = react_agent_node({
            "user_content": "选择：A. 卡通喜剧风。延续需求「生成猫抓老鼠的短剧」。请立刻按该选项推进",
            "intent": {"name": "workflow_orchestration", "wants_execution": True},
            "canvas_context": {"nodeCount": 0},
            "react_step": 0,
            "max_react_steps": 8,
            "selected_skill_keys": [],
            "observations": [],
            "executed_results": [],
            "recent_messages": [],
        })
    finally:
        ra._call_react_llm = old
        ra._structured_workflow_fallback = old_fb

    assert out["react_decision"] == "act"
    assert out.get("validation_route") == "execute"


def test_build_user_prompt_expands_a_and_lists_options():
    recent = [
        {
            "role": "assistant",
            "content": "想要哪种风格基调？",
            "next_actions": [
                "A. 卡通喜剧风（汤姆杰瑞式）",
                "B. 拟人剧情风",
            ],
        },
    ]
    body = build_user_prompt(user_content="A", recent_messages=recent)
    assert "卡通喜剧风" in body
    assert "上轮助手给出的可选项" in body
    assert "禁止声称上轮未给选项" in body or "必须按此选项推进" in body
