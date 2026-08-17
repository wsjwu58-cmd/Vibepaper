"""Reuse existing canvas workflow for compose — never scaffold again."""

from agent.domain.creative_planner import compile_execution_plan
from agent.domain.intent_classifier import deterministic_intent_match
from agent.domain.pipeline import canvas_has_workflow, plan_compose_existing, wants_direct_compose


def _canvas_with_compose():
    return {
        "nodeCount": 8,
        "creativeTypeCounts": {"clip": 6, "composite": 1, "script": 1},
        "nodeTypeCounts": {"video": 6, "compose": 1, "text": 2},
        "nodes": [
            {"id": 1, "type": "text", "creativeType": "script", "params": {"title": "总脚本"}},
            {"id": 10, "type": "video", "creativeType": "clip", "params": {"title": "镜头1"}, "status": "ready"},
            {"id": 11, "type": "video", "creativeType": "clip", "params": {"title": "镜头2"}, "status": "ready"},
            {
                "id": 99,
                "type": "compose",
                "creativeType": "composite",
                "params": {"title": "成片", "prompt": "拼接成片"},
                "prompt": "拼接成片",
                "status": "idle",
            },
        ],
        "edges": [],
    }


def test_direct_compose_intent():
    # 意图识别已改 LLM；此处只验证铁路复用的内容启发
    assert wants_direct_compose("直接合成")
    assert deterministic_intent_match("直接合成") is None


def test_plan_compose_existing_uses_compose_final_not_create():
    plan = plan_compose_existing(_canvas_with_compose())
    tools = [a.tool_name for a in plan.actions]
    assert "compose_final" in tools
    assert "create_nodes" not in tools


def test_compile_direct_compose_does_not_scaffold():
    assert canvas_has_workflow(_canvas_with_compose())
    plan = compile_execution_plan(
        "直接合成",
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={"thinking": "应直接合成"},
        canvas_context=_canvas_with_compose(),
    )
    tools = [(s.payload or {}).get("tool") for s in plan.steps]
    assert "compose_final" in tools
    assert "create_nodes" not in tools
    assert plan.workflow == "compose_existing"
