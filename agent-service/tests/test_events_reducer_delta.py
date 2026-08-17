"""Regression: operator.add events must receive deltas only."""

from __future__ import annotations

from agent.graph.nodes.orchestration_nodes import (
    classify_intent_node,
    create_plan_node,
    finalize_node,
    ingest_node,
    load_skill_node,
    select_skill_node,
    validate_plan_node,
)


def _base_state(**extra):
    state = {
        "session_id": 1,
        "user_id": 1,
        "canvas_id": 1,
        "user_content": "帮我生成吕布骑赤兔马战斗的短剧",
        "events": [{"type": "user_message", "content": "seed"}],
        "run_version": 0,
        "intent": {
            "name": "workflow_orchestration",
            "confidence": 0.96,
            "wants_execution": True,
            "requested_skill": "竖屏短剧",
            "reasons": ["test"],
        },
        "selected_skill_keys": ["vertical-short-drama"],
        "skill_name": "vertical-short-drama",
        "canvas_context": {"nodeCount": 0},
        "reply": "",
        "next_actions": [],
        "plan": {},
        "terminal_status": "running",
        "waiting_external_event": False,
        "pending_runs": [],
    }
    state.update(extra)
    return state


def test_nodes_return_event_deltas_not_full_history():
    """若节点回放历史 events，operator.add 会指数膨胀并卡死「正在工作」。"""
    seed = [{"type": "user_message", "content": "seed"}]
    out = ingest_node(_base_state(events=seed * 50))
    assert all(e.get("type") != "user_message" for e in out["events"])
    assert any(e.get("type") == "ingest" for e in out["events"])

    out = select_skill_node(_base_state(events=seed * 20))
    assert len(out["events"]) == 1
    assert out["events"][0]["type"] == "skill_selected"

    out = load_skill_node(_base_state(events=seed * 20))
    assert len(out["events"]) == 1
    assert out["events"][0]["type"] == "skill_loaded"

    # create_plan 无 api_key 时走脚手架，不应带回历史
    out = create_plan_node(_base_state(events=seed * 30))
    assert all(e.get("type") != "user_message" for e in out["events"])
    assert out.get("plan")

    out = validate_plan_node(_base_state(events=seed * 30, plan=out["plan"]))
    assert all(e.get("type") != "user_message" for e in (out.get("events") or []))

    out = finalize_node(_base_state(events=seed * 40, terminal_status="completed"))
    assert out["events"] == [{"type": "finalize", "terminal_status": "completed"}]


def test_events_reducer_replace_drops_history():
    from agent.graph.state import events_reducer, reset_events

    bloated = [{"type": "old", "i": i} for i in range(500)]
    merged = events_reducer(bloated, reset_events({"type": "user_message", "content": "hi"}))
    assert len(merged) == 1
    assert merged[0]["type"] == "user_message"
    # 增量追加
    merged2 = events_reducer(merged, [{"type": "ingest"}])
    assert [e["type"] for e in merged2] == ["user_message", "ingest"]


def test_short_drama_prompt_no_longer_uses_regex_intent():
    from agent.domain.intent_classifier import classify_intent_hybrid, deterministic_intent_match

    assert deterministic_intent_match("帮我生成吕布骑赤兔马战斗的短剧") is None
    offline = classify_intent_hybrid("帮我生成吕布骑赤兔马战斗的短剧", api_key=None)
    assert offline.name == "unknown"
    assert offline.wants_execution is True


def test_affirmative_yes_is_confirm_accept():
    from agent.graph.confirm_helpers import parse_confirm_intent

    assert parse_confirm_intent("是") == "accept"
    assert parse_confirm_intent("好") == "accept"
    assert parse_confirm_intent("继续") == "accept"
    assert parse_confirm_intent("取消") == "cancel"
