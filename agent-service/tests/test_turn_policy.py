"""回合纪律：过程话术不进对话，假提问不得打断任务。"""

from agent.domain.turn_policy import (
    can_proceed_without_user,
    is_genuine_user_gap,
    is_process_narration,
    silence_process_reply,
)


def test_process_narration_and_fake_ask():
    assert is_process_narration("我先加载技能再创建节点")
    assert is_process_narration("接下来我会开始搭建工作流")
    assert is_process_narration("要我开始吗")
    assert not is_process_narration("主角是猫还是拟人？")
    assert silence_process_reply("我先读取画布") == ""
    assert silence_process_reply("主角叫什么名字？", keep_if_genuine_ask=True) == "主角叫什么名字？"


def test_can_proceed_with_theme_or_steps():
    assert can_proceed_without_user(
        content="创建猫抓老鼠的短剧",
        wants_execution=True,
        has_steps=False,
    )
    assert can_proceed_without_user(
        content="做一个30秒短剧",
        wants_execution=True,
        has_steps=True,
    )
    assert not can_proceed_without_user(
        content="做一个30秒短剧",
        wants_execution=True,
        has_steps=False,
    )


def test_genuine_gap_only_when_empty_and_no_theme():
    assert is_genuine_user_gap(
        question="想拍什么主题？",
        content="做一个30秒短剧",
        wants_execution=True,
        has_steps=False,
    )
    assert not is_genuine_user_gap(
        question="我先加载技能可以吗？",
        content="创建猫抓老鼠的短剧",
        wants_execution=True,
        has_steps=False,
    )
    assert not is_genuine_user_gap(
        question="要我开始吗",
        content="做一个30秒短剧",
        wants_execution=True,
        has_steps=True,
    )
