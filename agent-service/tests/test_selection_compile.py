"""选中节点贯通 creative_planner + 多选派生。"""

from __future__ import annotations

from agent.agent.planner import _plan_create_media
from agent.domain.creative_planner import compile_execution_plan
from agent.domain.llm_prompt import _canvas_brief, build_user_prompt


def _tools(plan) -> list[str]:
    return [(s.payload or {}).get("tool") for s in plan.steps]


def test_compile_simple_media_with_selected_connects():
    plan = compile_execution_plan(
        "根据选中文本生成一张海报",
        intent_name="direct_canvas_action",
        requested_skill=None,
        creative={"thinking": "派生"},
        canvas_context={
            "nodes": [{"id": 11, "type": "text", "x": 100, "y": 120, "prompt": "黑猫"}],
            "selectedNodes": [{"id": 11, "type": "text", "x": 100, "y": 120, "prompt": "黑猫"}],
        },
        selected_nodes=[11],
    )
    assert plan.workflow == "simple_media_create"
    tools = _tools(plan)
    assert "create_nodes" in tools
    assert "connect_nodes" in tools
    assert "submit_generation" in tools
    connect = next(s for s in plan.steps if (s.payload or {}).get("tool") == "connect_nodes")
    edge = (connect.payload or {})["params"]["edges"][0]
    assert edge["sourceNodeId"] == 11
    assert edge["targetNodeId"] == "$created[0]"


def test_compile_outpaint_process_route():
    plan = compile_execution_plan(
        "给这张图扩图",
        intent_name="direct_canvas_action",
        requested_skill=None,
        creative={},
        canvas_context={"nodes": [{"id": 5, "type": "image"}]},
        selected_nodes=[5],
    )
    assert plan.workflow == "media_process:outpaint"
    assert "outpaint" in _tools(plan)


def test_compile_upscale_without_selection_asks_canvas():
    plan = compile_execution_plan(
        "超分",
        intent_name="direct_canvas_action",
        requested_skill=None,
        creative={},
        canvas_context={},
        selected_nodes=[],
    )
    assert plan.workflow == "media_process:upscale"
    assert _tools(plan)[0] == "get_canvas_summary"


def test_plan_create_media_dual_images_for_video():
    canvas = {
        "selectedNodes": [
            {"id": 1, "type": "image", "x": 0, "y": 0},
            {"id": 2, "type": "image", "x": 100, "y": 0},
            {"id": 3, "type": "text", "x": 50, "y": 80, "prompt": "旁白"},
        ],
        "nodes": [],
    }
    actions = _plan_create_media("用这两张图做首尾帧视频", [1, 2, 3], canvas)
    connect = next(a for a in actions if a.tool_name == "connect_nodes")
    srcs = [e["sourceNodeId"] for e in connect.params["edges"]]
    # 两张图优先，文本随后
    assert srcs[:2] == [1, 2]
    assert 3 in srcs
    assert actions[-1].params["node_id"] == "$created[0]"
    assert actions[-1].params["model_type"] == "video"


def test_canvas_brief_includes_selected_detail():
    brief = _canvas_brief({
        "nodeCount": 2,
        "selectedNodes": [{
            "id": 9,
            "type": "image",
            "prompt": "完整提示词不应只剩 id",
            "params": {"model": "agnes-image", "title": "参考"},
            "upstream": [{"id": 1, "type": "text"}],
            "hasOutput": True,
        }],
    })
    assert brief["selectedNodes"][0]["prompt"]
    assert brief["selectedNodes"][0]["params"]["model"] == "agnes-image"


def test_user_prompt_surfaces_selected_detail():
    text = build_user_prompt(
        user_content="生成视频",
        canvas_context={
            "selectedNodes": [{"id": 7, "type": "image", "prompt": "猫"}],
        },
        selected_nodes=[7],
    )
    assert "选中节点完整信息" in text
    assert "猫" in text
