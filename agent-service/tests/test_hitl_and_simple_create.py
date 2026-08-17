"""回归：闲聊必回、独立创建不被成片铁路劫持、确认走 HITL 恢复。"""

from __future__ import annotations

from agent.domain.creative_planner import compile_execution_plan
from agent.domain.intent_classifier import classify_intent_hybrid, is_chitchat
from agent.domain.pipeline import wants_new_independent_create
from agent.graph.confirm_helpers import parse_confirm_intent
from agent.graph.nodes.orchestration_nodes import answer_discussion_node
from agent.graph.nodes.reply_builder import reply_builder_node


def test_chitchat_detection():
    assert is_chitchat("你好")
    assert is_chitchat("Hello!")
    assert not is_chitchat("创建一个小狗图片")


def test_chitchat_intent_offline():
    intent = classify_intent_hybrid("你好", api_key=None)
    assert intent.name == "discussion"
    assert intent.wants_execution is False


def test_answer_discussion_always_replies_to_hello():
    out = answer_discussion_node({
        "user_content": "你好",
        "canvas_context": {},
        "selected_nodes": [],
        "recent_messages": [],
    })
    assert out["reply"]
    assert "Paper Agent" in out["reply"] or "你好" in out["reply"]
    assert out["reply_type"] == "directions"


def test_reply_builder_emits_discussion_reply():
    out = reply_builder_node({
        "reply": "你好，我是 Paper Agent。",
        "reply_type": "directions",
        "events": [],
        "executed_results": [],
        "next_actions": ["创建一张图片"],
        "canvas_context": {},
    })
    assert out["reply"]
    assert out.get("events")
    assert out["events"][0]["type"] == "assistant_message"


def test_independent_puppy_not_hijacked_by_compose_ready():
    assert wants_new_independent_create("创建一个小狗图片，独立的")
    canvas = {
        "nodeCount": 8,
        "creativeTypeCounts": {"composite": 1, "clip": 3},
        "nodeTypeCounts": {"compose": 1, "video": 3},
    }
    plan = compile_execution_plan(
        "创建一个小狗图片，独立的",
        intent_name="direct_canvas_action",
        requested_skill=None,
        creative={"thinking": "创意规划降级：Expecting value"},
        canvas_context=canvas,
    )
    tools = [(s.payload or {}).get("tool") for s in plan.steps]
    assert "create_nodes" in tools
    assert "submit_generation" in tools
    assert plan.workflow == "simple_media_create"
    assert "成片已就绪" not in (plan.reply or "")


def test_confirm_parse():
    assert parse_confirm_intent("确认") == "accept"
    assert parse_confirm_intent("取消") == "cancel"
