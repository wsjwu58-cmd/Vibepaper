"""七大工作方式端到端审计：提出创作需求 → 规划 → 逐条原则验收。"""

from __future__ import annotations

from agent.agent.planner import _infer_node_type, llm_plan_structured, plan
from agent.domain.methodology import assert_methodology, audit_plan_result
from agent.domain.workflow_orchestrator import (
    plan_advance_workflow_layer,
    plan_short_drama_workflow,
    plan_workflow_orchestration,
)


USER_SHORT_DRAMA = "做一个30秒短剧，3个镜头，主角是穿靴子的橘猫在雨夜城门前"


def test_e2e_short_drama_follows_seven_principles():
    """整体测试：用户要一条短剧链路，Agent 必须按七大原则走出完整流程。"""
    result = plan_workflow_orchestration(USER_SHORT_DRAMA, {"nodes": [], "edges": []}, [])
    report = audit_plan_result(result, USER_SHORT_DRAMA, expect_multi_unit=True)
    assert report.ok, report.as_dict()

    tools = [a.tool_name for a in result.actions]
    # 一：核心循环落在真实动作上
    assert "create_nodes" in tools
    assert "connect_nodes" in tools
    assert "submit_generation" in tools
    assert tools.index("create_nodes") < tools.index("submit_generation")

    # 二/三：产物边界 + 类型
    nodes = []
    for a in result.actions:
        if a.tool_name == "create_nodes":
            nodes.extend(a.params.get("nodes") or [])
    creatives = {n.get("creativeType") for n in nodes}
    assert {"script", "character", "shot", "keyframe", "clip", "composite"} <= creatives
    assert sum(1 for n in nodes if n.get("creativeType") == "keyframe") == 3
    assert sum(1 for n in nodes if n.get("creativeType") == "clip") == 3
    for n in nodes:
        if n.get("creativeType") == "keyframe":
            assert n["type"] == "image"
        if n.get("creativeType") == "clip":
            assert n["type"] == "video"

    # 四：input 依赖链 + 布局
    assert "layout_nodes" in tools
    edges = []
    for a in result.actions:
        if a.tool_name == "connect_nodes":
            edges.extend(a.params.get("edges") or [])
    assert edges and all(e.get("dependencyType") == "input" for e in edges)

    # 五：独立 prompt，非用户原话
    prompts = [n.get("prompt") or (n.get("params") or {}).get("prompt") for n in nodes]
    assert all(prompts) and len(set(prompts)) == len(prompts)
    assert USER_SHORT_DRAMA not in prompts

    # 六：只提交链起点；回复承认 queued 不是成品
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["node_id"] == "$created[0]"
    assert submits[0].params["model_type"] == "text"
    assert "compose_final" not in tools
    assert "queued" in result.reply or "不是成品" in result.reply
    assert "已经生成好了" not in result.reply

    # 七：创作术语 + 不暴露内部 id
    assert any(t in result.reply for t in ("分镜", "镜头", "首帧", "成片"))
    assert "节点 0" not in result.reply
    assert "$created" not in result.reply
    assert "转场" in result.reply or "留白" in result.reply  # 有主见


def test_e2e_image_then_video_waits_for_keyframe():
    msg = "先生成一张穿铠甲的狼的图片，再根据图片生成视频"
    actions = plan(msg, {"nodes": [], "edges": []}, [])
    from agent.agent.planner import PlanResult

    result = PlanResult(
        actions=actions,
        reply="已铺首帧与视频节点，先提交首帧生成。",
        thinking="先定视觉锚点再做动态镜头",
    )
    assert_methodology(result, msg, expect_multi_unit=False)
    submits = [a for a in actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["model_type"] == "image"


def test_advance_video_layer_skips_submit_when_keyframe_not_ready():
    ctx = {
        "nodes": [
            {"id": 1, "type": "text", "creativeType": "shot", "execStatus": "ready",
             "prompt": "三镜头分镜表……", "x": 100, "y": 100},
            {"id": 2, "type": "image", "creativeType": "keyframe", "execStatus": "running",
             "prompt": "镜头1首帧：橘猫远景", "params": {"title": "镜头1首帧"}, "x": 400, "y": 80},
            {"id": 3, "type": "image", "creativeType": "keyframe", "execStatus": "idle",
             "prompt": "镜头2首帧：城门特写", "params": {"title": "镜头2首帧"}, "x": 400, "y": 220},
        ],
        "edges": [
            {"source": 1, "target": 2, "dependencyType": "input"},
            {"source": 1, "target": 3, "dependencyType": "input"},
        ],
    }
    result = plan_advance_workflow_layer(ctx, None)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert submits == []
    assert "create_nodes" in [a.tool_name for a in result.actions]
    assert "自动提交" in result.reply or "尚未就绪" in result.reply


def test_advance_video_layer_submits_only_ready_keyframes():
    ctx = {
        "nodes": [
            {"id": 1, "type": "text", "creativeType": "shot", "execStatus": "ready",
             "prompt": "分镜", "x": 100, "y": 100},
            {"id": 2, "type": "image", "creativeType": "keyframe", "execStatus": "ready",
             "prompt": "镜头1首帧：橘猫远景雨夜", "params": {"title": "镜头1首帧"}, "x": 400, "y": 80},
            {"id": 3, "type": "image", "creativeType": "keyframe", "execStatus": "running",
             "prompt": "镜头2首帧：城门", "params": {"title": "镜头2首帧"}, "x": 400, "y": 220},
        ],
        "edges": [
            {"source": 1, "target": 2, "dependencyType": "input"},
            {"source": 1, "target": 3, "dependencyType": "input"},
        ],
    }
    result = plan_advance_workflow_layer(ctx, None)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["node_id"] == "$created[0]"


def test_infer_node_type_media_over_subject():
    assert _infer_node_type("生成一段角色视频") == "video"
    assert _infer_node_type("画一张角色海报") == "image"
    assert _infer_node_type("写一段旁白配音") == "audio"


def test_llm_plan_structured_no_longer_scaffolds_short_drama():
    """编排主路径已迁 ReAct；此处不再硬搭短剧空壳脚手架。"""
    result = llm_plan_structured(
        content=USER_SHORT_DRAMA,
        canvas_context={"nodes": [], "edges": []},
        selected_nodes=[],
        recent_messages=[],
        skill_instructions="",
        api_key="sk-test",
        base_url="https://example.invalid",
        model="dummy",
    )
    creates = [a for a in result.actions if a.tool_name == "create_nodes"]
    total_nodes = sum(len((a.params or {}).get("nodes") or []) for a in creates)
    assert total_nodes < 6
    for a in creates:
        for n in a.params.get("nodes") or []:
            p = str(n.get("prompt") or (n.get("params") or {}).get("prompt") or "")
            assert "请直接写出" not in p


def test_character_card_only_when_requested():
    plain = plan_short_drama_workflow("做一个30秒短剧，3个镜头", None)
    nodes = []
    for a in plain.actions:
        if a.tool_name == "create_nodes":
            nodes.extend(a.params.get("nodes") or [])
    assert not any(n.get("creativeType") == "character" for n in nodes)

    with_char = plan_short_drama_workflow(
        "做一个30秒短剧，3个镜头，主角是黑猫", None,
    )
    nodes2 = []
    for a in with_char.actions:
        if a.tool_name == "create_nodes":
            nodes2.extend(a.params.get("nodes") or [])
    assert any(n.get("creativeType") == "character" for n in nodes2)


def test_orphan_nodes_still_bootstrap_short_drama():
    """画布有无关节点但无 script/shot 时，不得只读画布空转。"""
    orphan_ctx = {
        "nodes": [
            {"id": 99, "type": "text", "status": "idle", "prompt": "旧草稿"},
            {"id": 100, "type": "image", "status": "idle"},
        ],
        "edges": [],
        "nodeCount": 2,
    }
    for msg in (
        "根据工作流生成橘猫和恶狼战斗的短剧",
        "搭建短剧工作流",
    ):
        result = plan_workflow_orchestration(msg, orphan_ctx, [])
        tools = [a.tool_name for a in result.actions]
        assert "create_nodes" in tools, msg
        assert "submit_generation" in tools, msg
        assert tools.count("get_canvas_summary") == 0 or "create_nodes" in tools
        # 不能只剩读画布
        assert not (tools == ["get_canvas_summary"]), msg
        assert "各层都有产物" not in (result.actions[0].reasoning or "")


def test_advance_without_pipeline_does_not_claim_ready():
    """无流水线时 advance 兜底不得谎称各层都有产物。"""
    result = plan_advance_workflow_layer(
        {"nodes": [{"id": 1, "type": "text"}], "edges": []},
        None,
    )
    tools = [a.tool_name for a in result.actions]
    assert tools == ["get_canvas_summary"]
    assert "各层都有产物" not in (result.actions[0].reasoning or "")
    assert "还没有短剧流水线" in result.reply or "搭建短剧" in result.reply
