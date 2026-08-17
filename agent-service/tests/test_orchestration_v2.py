# -*- coding: utf-8 -*-
"""Orchestration v2 unit tests: LLM intent, skills, prompt layers."""

from agent.domain.creative_planner import (
    compile_execution_plan,
    infer_trim_from_user,
    steps_to_planned_actions,
)
from agent.domain.intent_classifier import (
    classify_intent_hybrid,
    deterministic_intent_match,
    route_intent_name,
)
from agent.domain.llm_prompt import build_chat_messages, build_user_prompt, tools_catalog_for_prompt
from agent.domain.skill_catalog import (
    SKILL_CATALOG,
    SKILL_ROUTES,
    compile_profile_for,
    primary_skill_key,
    resolve_route_keys,
    trim_skeleton,
)
from agent.domain.prompt_builder import build_node_prompt, is_verbatim_user_dump
from agent.graph.nodes.orchestration_nodes import select_skill_node
from agent.domain.plan_models import IntentResult


def test_deterministic_intent_removed():
    assert deterministic_intent_match("comic layout?") is None
    assert deterministic_intent_match("generate comic") is None
    assert deterministic_intent_match("continue") is None


def test_route_intent_names():
    from agent.domain.plan_models import IntentResult

    assert route_intent_name(IntentResult(name="discussion", wants_execution=False)) == "answer_discussion"
    assert route_intent_name(IntentResult(name="advance_pipeline", wants_execution=True)) == "reconcile_canvas"
    assert route_intent_name(IntentResult(name="workflow_orchestration", wants_execution=True)) == "select_skill"


def test_hybrid_without_llm_falls_back_without_regex():
    r = classify_intent_hybrid("make a movie poster", api_key=None)
    assert r.name == "unknown"
    assert r.wants_execution is True
    assert r.confidence <= 0.5


def test_empty_input_is_discussion_offline():
    r = classify_intent_hybrid("", api_key=None)
    assert r.name == "discussion"
    assert r.wants_execution is False


def test_prompt_layers_put_user_first_and_list_tools_skills():
    user_goal = "help generate orange-cat short drama"
    messages = build_chat_messages(
        user_content=user_goal,
        persona="You are DD.",
        skill_instructions="Skill rules sample",
        include_tools=True,
        include_skills_catalog=True,
        recent_messages=[{"role": "user", "content": "prefer vertical"}],
        observations=[{"tool": "load_skill", "ok": True, "summary": "loaded"}],
        canvas_context={"nodeCount": 3},
    )
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    system = messages[0]["content"]
    user = messages[1]["content"]
    assert "get_canvas_summary" in system
    assert "vertical-short-drama" in system
    assert "system" in system.lower() or "Skill" in system or "工具" in system
    assert user_goal in user
    assert "load_skill" in user
    assert "prefer vertical" in user
    # user instruction section must appear before the goal text
    assert user.index("最高优先级") < user.index(user_goal) or user.index("PRIORITY") < user.index(user_goal) or "【本轮用户指令" in user


def test_tools_catalog_non_empty():
    text = tools_catalog_for_prompt()
    assert "create_nodes" in text
    assert "submit_generation" in text


def test_user_prompt_priority_marker():
    body = build_user_prompt(user_content="do what I said first")
    assert "do what I said first" in body
    assert body.index("【本轮用户指令｜最高优先级】") < body.index("do what I said first")


def test_skill_catalog_complete():
    assert "vertical-short-drama" in SKILL_CATALOG
    assert "storyboard-shot-list" in SKILL_CATALOG
    assert "six-panel-comic" in SKILL_CATALOG
    assert "character-consistency" in SKILL_CATALOG
    assert "竖屏短剧" in SKILL_ROUTES
    keys = resolve_route_keys("竖屏短剧")
    assert "vertical-short-drama" in keys
    assert "storyboard-shot-list" in keys


def test_trim_skeleton_skip_character():
    sk = SKILL_CATALOG["vertical-short-drama"].workflow_skeleton
    trimmed = trim_skeleton(sk, skip_labels=["角色"])
    assert all("角色" not in x for x in trimmed)


def test_infer_trim_and_compile_short_drama():
    trim = infer_trim_from_user("跳过角色卡，搭建竖屏短剧")
    assert any("角色" in x for x in trim["skip_labels"])

    plan = compile_execution_plan(
        "搭建橘猫短剧三镜头",
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={
            "goal": "橘猫短剧",
            "shots": [
                {"index": 1, "title": "镜头1", "keyframe_prompt": "猫站门口", "clip_prompt": "猫推门"},
                {"index": 2, "title": "镜头2", "keyframe_prompt": "对峙", "clip_prompt": "镜头推进"},
                {"index": 3, "title": "镜头3", "keyframe_prompt": "反转", "clip_prompt": "甩尾离开"},
            ],
            "script_prompt": "总脚本内容",
            "storyboard_prompt": "分镜内容",
            "skip_steps": ["角色"],
        },
    )
    assert plan.workflow == "vertical-short-drama"
    tools = [s.payload.get("tool") for s in plan.steps]
    assert "create_nodes" in tools
    assert "connect_nodes" in tools
    assert "submit_generation" in tools
    actions = steps_to_planned_actions(plan)
    assert any(a["tool_name"] == "create_nodes" for a in actions)


def test_compile_only_script_stop():
    plan = compile_execution_plan(
        "只要剧本",
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={"stop_after": "剧本", "script_prompt": "一集剧本", "shots": []},
    )
    titles = " ".join(s.title for s in plan.steps)
    assert "首帧" not in titles or "文本" in titles


def test_compile_refuses_empty_template_scaffold():
    plan = compile_execution_plan(
        "直接合成",
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={},
    )
    assert plan.steps == []
    assert plan.user_decision_required
    assert "空模板" in (plan.reply or "") or "请" in (plan.reply or "")

    plan2 = compile_execution_plan(
        "做一个30秒短剧",
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={"from_llm": True, "shots": [], "script_prompt": ""},
    )
    assert plan2.steps == []
    assert plan2.user_decision_required


def test_primary_skill_prefers_short_drama_in_route():
    keys = resolve_route_keys("竖屏短剧")
    assert keys[0] == "manga-story-bible"
    assert primary_skill_key(keys) == "vertical-short-drama"
    assert compile_profile_for(primary_skill_key(keys)) == "short_drama"
    assert compile_profile_for("film-poster") == "simple_visual"
    assert compile_profile_for("storyboard-shot-list") == "text_chain"


def test_select_skill_does_not_default_to_short_drama():
    out = select_skill_node({
        "intent": {
            "name": "workflow_orchestration",
            "confidence": 0.9,
            "wants_execution": True,
            "requested_skill": None,
        },
        "skill_name": "paper-agent-default",
    })
    assert out["selected_skill_keys"] == []


def test_select_skill_honors_llm_choice():
    out = select_skill_node({
        "intent": IntentResult(
            name="workflow_orchestration",
            confidence=0.9,
            wants_execution=True,
            requested_skill="六格漫画",
        ).model_dump(),
        "skill_name": "x",
    })
    assert out["selected_skill_keys"][0] == "six-panel-comic"


def test_compile_film_poster_not_short_drama():
    plan = compile_execution_plan(
        "做一张竖版电影海报，片名赤壁",
        intent_name="workflow_orchestration",
        requested_skill="电影海报",
        creative={"script_prompt": "赤壁：火焰江面，大字片名，9:16 电影海报构图"},
    )
    assert plan.workflow == "film-poster"
    titles = " ".join(s.title for s in plan.steps)
    assert "成片" not in titles
    assert "视频" not in titles
    tools = [s.payload.get("tool") for s in plan.steps]
    assert "create_nodes" in tools
    nodes = []
    for s in plan.steps:
        if s.payload.get("tool") == "create_nodes":
            nodes.extend((s.payload.get("params") or {}).get("nodes") or [])
    assert len(nodes) == 1
    assert nodes[0]["type"] == "image"


def test_compile_storyboard_skill_is_text_chain():
    plan = compile_execution_plan(
        "把这段剧情拆成分镜表",
        intent_name="workflow_orchestration",
        requested_skill="storyboard-shot-list",
        creative={"storyboard_prompt": "三镜：远景建立、中景对峙、特写反转"},
        skill_keys=["storyboard-shot-list"],
    )
    assert plan.workflow == "storyboard-shot-list"
    nodes = []
    for s in plan.steps:
        if s.payload.get("tool") == "create_nodes":
            nodes.extend((s.payload.get("params") or {}).get("nodes") or [])
    types = {n.get("type") for n in nodes}
    assert "video" not in types
    assert "compose" not in types
    assert "text" in types


def test_node_prompts_are_not_user_utterance():
    user = "按照工作流生成橘猫和恶狼的短剧"
    plan = compile_execution_plan(
        user,
        intent_name="workflow_orchestration",
        requested_skill="竖屏短剧",
        creative={
            "script_prompt": user,
            "storyboard_prompt": user,
            "shots": [
                {"index": 1, "keyframe_prompt": user, "clip_prompt": user},
            ],
        },
    )
    prompts = []
    for s in plan.steps:
        if s.payload.get("tool") != "create_nodes":
            continue
        for node in (s.payload.get("params") or {}).get("nodes") or []:
            p = str(node.get("prompt") or (node.get("params") or {}).get("prompt") or "")
            if p:
                prompts.append(p)
                assert not is_verbatim_user_dump(p, user)
                assert p != user
    assert len(prompts) >= 3
    assert len(set(prompts)) == len(prompts)


def test_role_prompts_include_theme_but_differ():
    user = "做一个30秒短剧，3个镜头，主角是穿铠甲的狼"
    script = build_node_prompt(role="script", user_theme=user)
    shot = build_node_prompt(role="shot", user_theme=user, shot_count=3)
    assert script != user
    assert shot != script
    assert "铠甲" in script or "狼" in script
    assert "拆成" in shot or "镜" in shot
