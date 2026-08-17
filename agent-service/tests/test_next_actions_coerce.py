from agent.domain.plan_models import (
    StructuredPlan,
    extract_misplaced_actions,
    normalize_next_actions,
)


def test_next_actions_coerce_dict_to_string():
    plan = StructuredPlan(
        goal="短剧",
        next_actions=[
            {"type": "create_node", "summary": "创建吕布核心设定", "prompt": "核心设定和风格"},
            "推进下一阶段",
        ],
    )
    assert plan.next_actions[0] == "创建吕布核心设定"
    assert "推进下一阶段" in plan.next_actions


def test_extract_misplaced_actions_salvages_create_node():
    chips, actions = extract_misplaced_actions([
        {"type": "create_node", "node_type": "text", "prompt": "核心设定和风格", "summary": "写设定"},
        "直接合成",
    ])
    assert chips == ["直接合成"]
    assert len(actions) == 1
    assert actions[0]["tool"] == "create_nodes"
    assert actions[0]["params"]["nodes"][0]["prompt"] == "核心设定和风格"


def test_normalize_next_actions_filters_empty():
    assert normalize_next_actions([None, "", "  ok  ", {"tool": "x"}]) == ["ok", "x"]
