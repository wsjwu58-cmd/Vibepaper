"""ReAct 循环与 load_skill 按需加载。"""

from __future__ import annotations

from agent.graph.nodes.react_agent import actions_to_plan, react_agent_node
from agent.graph.routing import route_after_exec
from agent.tools.registry import TOOLS


def test_load_skill_resolves_catalog_key():
    out = TOOLS["load_skill"].fn(skill_key="storyboard-shot-list", user_id=1, canvas_id=1)
    assert "error" not in out
    assert out.get("skill_key") == "storyboard-shot-list"
    assert "分镜" in (out.get("instructions") or "") or "镜头" in (out.get("instructions") or "")


def test_load_skill_resolves_route_name():
    out = TOOLS["load_skill"].fn(skill_key="六格漫画", user_id=1, canvas_id=1)
    assert "error" not in out
    assert out.get("loaded_keys")
    assert out.get("instructions")


def test_actions_to_plan_maps_tools():
    plan = actions_to_plan(
        [
            {"tool": "load_skill", "params": {"skill_key": "six-panel-comic"}, "summary": "加载六格"},
            {"tool": "create_nodes", "params": {"nodes": []}, "summary": "建节点"},
        ],
        goal="六格",
        reply="ok",
        thinking="t",
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].kind == "load_skill"
    assert plan.steps[1].payload["tool"] == "create_nodes"


def test_route_after_exec_returns_reflect_on_failure():
    state = {
        "pending_high_risk": [],
        "executed_results": [
            {"tool": "create_nodes", "ok": False, "data": {"error": "boom"}},
        ],
        "contract_violations": [],
        "reflection_count": 0,
    }
    assert route_after_exec(state) == "reflect"


def test_route_after_exec_finish_goes_done():
    state = {
        "pending_high_risk": [],
        "executed_results": [
            {"tool": "create_nodes", "ok": True, "data": {}},
        ],
        "contract_violations": [],
        "reflection_count": 0,
    }
    assert route_after_exec(state) == "done"


def test_route_after_exec_react_act_continues():
    state = {
        "pending_high_risk": [],
        "executed_results": [
            {"tool": "load_skill", "ok": True, "data": {}},
        ],
        "contract_violations": [],
        "reflection_count": 0,
        "react_mode": True,
        "react_decision": "act",
        "react_step": 1,
        "max_react_steps": 8,
    }
    assert route_after_exec(state) == "continue"


def test_route_after_exec_ack_goes_clock():
    state = {
        "pending_high_risk": [],
        "executed_results": [
            {"tool": "submit_generation", "ok": True, "ack": True, "task_id": 99},
        ],
        "contract_violations": [],
        "reflection_count": 0,
    }
    assert route_after_exec(state) == "wait_for_result"


def test_react_forces_act_when_observation_failed(monkeypatch):
    import agent.graph.nodes.react_agent as ra

    def fake_llm(**kwargs):
        return {
            "thinking": "算了结束",
            "decision": "finish",
            "reply": "先到这里",
            "actions": [],
            "next_actions": [],
        }

    monkeypatch.setattr(ra, "_call_react_llm", fake_llm)
    monkeypatch.setattr(ra, "_structured_workflow_fallback", lambda state: None)
    out = ra.react_agent_node({
        "user_content": "继续搭建",
        "intent": {"name": "workflow_orchestration", "wants_execution": True},
        "canvas_context": {"nodeCount": 1},
        "react_step": 1,
        "max_react_steps": 8,
        "selected_skill_keys": [],
        "observations": [
            {"tool": "connect_nodes", "ok": False, "summary": "fail", "data": {"error": "bad edge"}},
        ],
        "executed_results": [],
        "recent_messages": [],
        "skill_instructions": "",
    })
    assert out["react_decision"] == "act"
    assert out.get("validation_route") == "execute"
    tools = [
        (s.payload or {}).get("tool")
        for s in __import__("agent.domain.plan_models", fromlist=["plan_from_dict"]).plan_from_dict(out["plan"]).steps
    ]
    assert "get_canvas_summary" in tools


def test_route_after_exec_ack_takes_priority_over_other_results():
    state = {
        "pending_high_risk": [],
        "executed_results": [
            {"tool": "submit_generation", "ok": True, "ack": True, "task_id": 99},
            {"tool": "load_skill", "ok": True, "data": {}},
        ],
        "contract_violations": [],
        "reflection_count": 0,
    }
    assert route_after_exec(state) == "wait_for_result"


def test_react_agent_cap_finishes(monkeypatch):
    state = {
        "user_content": "继续",
        "react_step": 8,
        "max_react_steps": 8,
        "reply": "已做一部分",
        "canvas_context": {},
        "intent": {},
        "observations": [],
        "selected_skill_keys": [],
        "skill_instructions": "",
    }
    out = react_agent_node(state)
    assert out["react_decision"] == "finish"
    assert out["validation_route"] == "finalize"


def test_react_agent_no_llm_narrow_or_finish(monkeypatch):
    from agent.core import config as cfg

    monkeypatch.setattr(cfg.settings, "llm_api_key", "")
    state = {
        "user_content": "生成黑猫视频",
        "react_step": 0,
        "max_react_steps": 8,
        "canvas_context": {"nodes": [], "edges": []},
        "intent": {"name": "direct_canvas_action"},
        "observations": [],
        "selected_skill_keys": [],
        "skill_instructions": "",
        "selected_nodes": [],
        "reply": "",
    }
    out = react_agent_node(state)
    assert out.get("react_mode") is True
    assert out.get("react_decision") in ("act", "finish")
    # 不应搭出巨型短剧脚手架
    plan = out.get("plan") or {}
    steps = plan.get("steps") or []
    assert len(steps) < 8


def test_react_empty_finish_rescues_short_drama(monkeypatch):
    """「创建…短剧」空 finish 必须编译出 create_nodes，禁止「本轮没有操作」。"""
    import agent.graph.nodes.react_agent as ra
    from agent.core import config as cfg

    monkeypatch.setattr(cfg.settings, "llm_api_key", "")
    monkeypatch.setattr(
        ra,
        "_call_react_llm",
        lambda **kwargs: {
            "thinking": "先想想",
            "decision": "finish",
            "reply": "",
            "actions": [],
            "next_actions": [],
        },
    )
    out = ra.react_agent_node({
        "user_content": "创建猫抓老鼠的短剧",
        "react_step": 0,
        "max_react_steps": 8,
        "canvas_context": {"nodes": [], "edges": [], "nodeCount": 0},
        # 故意误标 discussion + 不执行，验证 bootstrap 门闩仍能救回
        "intent": {"name": "discussion", "wants_execution": False},
        "observations": [],
        "selected_skill_keys": ["vertical-short-drama"],
        "skill_instructions": "",
        "selected_nodes": [],
        "recent_messages": [],
        "reply": "",
    })
    assert out["validation_route"] == "execute"
    assert "本轮没有需要执行的操作" not in (out.get("reply") or "")
    plan = out.get("plan") or {}
    tools = [
        (s.get("payload") or {}).get("tool")
        for s in (plan.get("steps") or [])
        if isinstance(s, dict)
    ]
    assert "create_nodes" in tools


def test_react_empty_finish_does_not_block_on_discussion_gate(monkeypatch):
    import agent.graph.nodes.react_agent as ra

    assert ra._looks_like_creative_bootstrap("创建猫抓老鼠的短剧") is True
    assert ra._looks_like_creative_bootstrap("生成黑猫视频") is False


def test_build_structured_plan_theme_backfill_when_llm_empty(monkeypatch):
    from agent.domain import creative_planner as cp

    monkeypatch.setattr(
        cp,
        "creative_plan_llm",
        lambda **kwargs: {
            "goal": "",
            "thinking": "",
            "reply": "",
            "shots": [],
            "script_prompt": "",
            "storyboard_prompt": "",
            "character_prompt": "",
            "next_actions": [],
        },
    )
    plan = cp.build_structured_plan(
        "创建猫抓老鼠的短剧",
        intent={"name": "workflow_orchestration", "wants_execution": True},
        skill_keys=["vertical-short-drama"],
        canvas_context={"nodes": [], "edges": []},
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test",
    )
    assert plan.steps, "主题可用时应编译出步骤，不能空壳拒绝"
    tools = [(s.payload or {}).get("tool") for s in plan.steps]
    assert "create_nodes" in tools


def test_react_process_talk_does_not_stop_or_chat(monkeypatch):
    """过程话术 + 假 ask_user：必须继续执行，对话气泡保持空。"""
    import agent.graph.nodes.react_agent as ra
    from agent.core import config as cfg

    monkeypatch.setattr(cfg.settings, "llm_api_key", "")
    monkeypatch.setattr(
        ra,
        "_call_react_llm",
        lambda **kwargs: {
            "thinking": "我先加载技能再创建节点",
            "decision": "ask_user",
            "ask_question": "我先加载技能可以吗？",
            "reply": "接下来我会开始搭建工作流",
            "actions": [],
            "next_actions": ["开始搭建"],
        },
    )
    out = ra.react_agent_node({
        "user_content": "创建猫抓老鼠的短剧",
        "react_step": 0,
        "max_react_steps": 8,
        "canvas_context": {"nodes": [], "edges": [], "nodeCount": 0},
        "intent": {"name": "workflow_orchestration", "wants_execution": True},
        "observations": [],
        "selected_skill_keys": ["vertical-short-drama"],
        "skill_instructions": "",
        "selected_nodes": [],
        "recent_messages": [],
        "reply": "",
    })
    assert out["react_decision"] != "ask_user"
    assert out.get("validation_route") == "execute"
    assert out.get("needs_user_input") is not True
    assert not (out.get("reply") or "").strip()
    tools = [
        (s.get("payload") or {}).get("tool")
        for s in ((out.get("plan") or {}).get("steps") or [])
        if isinstance(s, dict)
    ]
    assert "create_nodes" in tools or "get_canvas_summary" in tools


def test_react_act_silences_process_reply(monkeypatch):
    import agent.graph.nodes.react_agent as ra

    monkeypatch.setattr(
        ra,
        "_call_react_llm",
        lambda **kwargs: {
            "thinking": "先读画布",
            "decision": "act",
            "reply": "我先读取画布再创建节点",
            "actions": [{"tool": "get_canvas_summary", "params": {}, "summary": "读画布"}],
            "next_actions": [],
        },
    )
    monkeypatch.setattr(ra, "_structured_workflow_fallback", lambda state: None)
    out = ra.react_agent_node({
        "user_content": "生成黑猫视频",
        "intent": {"name": "direct_canvas_action", "wants_execution": True},
        "canvas_context": {"nodes": [], "edges": []},
        "react_step": 0,
        "max_react_steps": 8,
        "selected_skill_keys": [],
        "observations": [],
        "executed_results": [],
        "recent_messages": [],
        "skill_instructions": "",
        "selected_nodes": [],
        "reply": "",
    })
    assert out["react_decision"] == "act"
    assert (out.get("reply") or "") == ""
    assert any(e.get("type") == "thinking" for e in out.get("events") or [])


def test_validate_plan_ignores_fake_ask_when_steps_exist():
    from agent.domain.plan_models import PlanStep, StructuredPlan, plan_to_dict
    from agent.graph.nodes.orchestration_nodes import validate_plan_node

    plan = StructuredPlan(
        goal="短剧",
        user_decision_required=True,
        reply="我先加载技能可以吗？",
        constraints={"ask_question": "要我开始搭建吗"},
        steps=[
            PlanStep(
                id="s1",
                kind="edit",
                title="创建节点",
                payload={"tool": "create_nodes", "params": {}},
            ),
        ],
    )
    out = validate_plan_node({
        "plan": plan_to_dict(plan),
        "user_content": "创建猫抓老鼠的短剧",
        "intent": {"name": "workflow_orchestration", "wants_execution": True},
        "selected_nodes": [],
        "canvas_context": {},
        "reply": plan.reply,
        "next_actions": [],
    })
    assert out["validation_route"] == "execute"
    assert out.get("needs_user_input") is not True
    assert not (out.get("reply") or "").strip()


def test_reply_builder_strips_process_narration_without_results():
    from agent.graph.nodes.reply_builder import reply_builder_node

    out = reply_builder_node({
        "reply": "我先加载技能，接下来开始搭建工作流",
        "reply_type": "general",
        "pipeline_stage": "text_base",
        "executed_results": [],
        "pending_high_risk": [],
        "next_actions": [],
        "events": [],
        "needs_user_input": False,
    })
    assert (out.get("reply") or "") == ""
    assert not any(e.get("type") == "assistant_message" for e in out.get("events") or [])
