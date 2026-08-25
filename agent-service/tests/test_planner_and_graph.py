"""Agent 核心：意图分类、风险分级、图编译冒烟。"""

from agent.agent.planner import classify_intent, infer_query_scope, plan, detect_pipeline_stage
from agent.domain.creative_contract import validate_action, validate_generation
from agent.domain.dependency_graph import topo_sort_executable, walk_input_upstream
from agent.domain.pipeline import plan_advance_pipeline, plan_reregenerate_stale
from agent.tools.registry import TOOLS, classify_risk
from agent.graph.app import build_graph, build_wakeup_graph
from agent.graph.memory_subgraph import build_memory_subgraph
from langgraph.checkpoint.memory import MemorySaver


def test_paper_intents():
    assert classify_intent("帮我梳理这张画布") == "summarize"
    assert classify_intent("写一句品牌文案") == "copy"
    assert classify_intent("给我三个方向") == "directions"
    assert classify_intent("推进下一阶段") == "advance_pipeline"
    assert classify_intent("重跑 stale 节点") == "reregenerate_stale"
    assert infer_query_scope("summarize") == "summary"
    assert infer_query_scope("generate") == "selected"


def test_rule_plan_no_fake_copy():
    actions = plan("写一句品牌文案", {"nodes": [], "edges": []}, [])
    assert all(a.tool_name.startswith(("get_", "list_", "search_")) for a in actions)


def test_collab_tools_registered():
    for name in ("update_memory", "clock", "load_skill", "check_task_status"):
        assert name in TOOLS
        assert TOOLS[name].risk_level == "read"


def test_p2_tools_registered():
    for name in ("extract_frames", "trim_clip", "upscale", "outpaint", "compose_final", "capture_3d_scene"):
        assert name in TOOLS
        assert TOOLS[name].category == "p2"
        risk, _ = classify_risk(name, {"estimated_cost": 10, "node_id": 1}, None)
        assert risk == "high"


def test_submit_is_high_risk():
    risk, reason = classify_risk("submit_generation", {"estimated_cost": 10}, None)
    assert risk == "high"


def test_pipeline_stage():
    assert detect_pipeline_stage({"creativeTypeCounts": {"shot": 2}}) == "storyboard"
    assert detect_pipeline_stage({"nodeTypeCounts": {"video": 1}}) == "dynamic_gen"


def test_orchestrate_workflow_intent():
    assert classify_intent("帮我编排短剧工作流") == "orchestrate_workflow"
    assert classify_intent("搭建分镜链路") == "orchestrate_workflow"


def test_short_drama_workflow_plan():
    from agent.domain.workflow_orchestrator import plan_short_drama_workflow
    result = plan_short_drama_workflow("做一个30秒短剧，3个镜头", None)
    tools = [a.tool_name for a in result.actions]
    assert "create_nodes" in tools
    assert "connect_nodes" in tools
    assert "submit_generation" in tools
    assert result.reply_type == "pipeline"
    assert len([a for a in result.actions if a.tool_name == "create_nodes"]) >= 3


def test_node_feed_rules():
    from agent.domain.workflow_orchestrator import can_feed
    assert can_feed("text", "image")
    assert can_feed("image", "video")
    assert can_feed("audio", "video")
    assert not can_feed("audio", "compose")


def test_placeholder_connect_skips_contract():
    ctx = {"nodes": [], "edges": []}
    err = validate_action({
        "tool_name": "connect_nodes",
        "params": {"edges": [{"sourceNodeId": "$created[0]", "targetNodeId": "$created[1]", "dependencyType": "input"}]},
    }, ctx)
    assert err is None


def test_advance_pipeline_plan():
    result = plan_advance_pipeline({"creativeTypeCounts": {"script": 1}}, [])
    assert any(a.tool_name == "create_nodes" for a in result.actions)
    assert result.reply_type == "pipeline"


def test_reregenerate_stale_topo_order():
    ctx = {
        "staleNodes": [{"nodeId": 2, "type": "video"}, {"nodeId": 3, "type": "video"}],
        "nodes": [{"id": 1}, {"id": 2}, {"id": 3}],
        "edges": [
            {"source": 1, "target": 2, "dependencyType": "input"},
            {"source": 2, "target": 3, "dependencyType": "input"},
        ],
    }
    result = plan_reregenerate_stale(ctx)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    ids = [a.params["node_id"] for a in submits]
    assert ids.index(2) < ids.index(3)


def test_dependency_walk():
    nodes = [{"id": 1, "creativeType": "script"}, {"id": 2, "creativeType": "keyframe"}]
    edges = [{"source": 1, "target": 2, "dependencyType": "input"}]
    chain = walk_input_upstream(edges, nodes, 2)
    assert chain[0]["id"] == 1


def test_topo_sort():
    nodes = [{"id": 1}, {"id": 2}, {"id": 3}]
    edges = [
        {"source": 1, "target": 2, "dependencyType": "input"},
        {"source": 2, "target": 3, "dependencyType": "input"},
    ]
    order = topo_sort_executable(nodes, edges, [2, 3])
    assert order.index(2) < order.index(3)


def test_creative_contract_blocks_script_to_video():
    ctx = {
        "nodes": [{"id": 1, "type": "text", "creativeType": "script"}],
        "edges": [],
    }
    err = validate_generation(1, "video", ctx)
    assert err is not None
    assert "脚本" in err


def test_creative_contract_validate_action():
    ctx = {
        "nodes": [{"id": 1, "type": "text", "creativeType": "script"}],
        "edges": [],
    }
    err = validate_action({"tool_name": "submit_generation", "params": {"node_id": 1, "model_type": "video"}}, ctx)
    assert err is not None


def test_graph_compiles():
    g = build_graph(MemorySaver())
    assert g is not None


def test_wakeup_graph_compiles():
    g = build_wakeup_graph(MemorySaver())
    assert g is not None


def test_memory_subgraph_compiles():
    g = build_memory_subgraph()
    assert g is not None


def test_image_to_video_duration_from_text():
    actions = plan(
        "根据当前黑黄猫打架图片生成2秒视频",
        {"nodes": [{"id": 101, "type": "image", "execStatus": "ready"}], "edges": []},
        [101],
    )
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["model_params"]["duration"] == 2
    create = next(a for a in actions if a.tool_name == "create_nodes")
    assert create.params["nodes"][0]["params"]["duration"] == 2


def test_video_duration_from_node_params():
    from agent.domain.video_task import resolve_video_duration

    assert resolve_video_duration(content="", node_params={"duration": 4}) == 4
    assert resolve_video_duration(content="30秒短剧3个镜头", shot_count=3) == 10


def test_confirm_helpers():
    from agent.graph.confirm_helpers import parse_confirm_intent, should_auto_confirm

    assert parse_confirm_intent("确认") == "accept"
    assert parse_confirm_intent("取消") == "cancel"
    assert should_auto_confirm("根据图片生成2秒视频", "submit_generation") is True
    assert should_auto_confirm("帮我看看画布", "submit_generation") is False
