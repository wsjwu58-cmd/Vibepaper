"""扩图/超分/抽帧/剪辑：规划与派生行为。"""

from __future__ import annotations

from unittest.mock import patch

from agent.agent.planner import classify_intent, plan
from agent.tools.registry import TOOLS, _derive_and_operate


def test_classify_process_intents():
    assert classify_intent("给这张图扩图") == "outpaint"
    assert classify_intent("超分一下") == "upscale"
    assert classify_intent("提取关键帧") == "extract_frames"
    assert classify_intent("剪辑前3秒") == "trim_clip"


def test_plan_outpaint_with_selected():
    actions = plan("扩图", {"nodes": [], "edges": []}, [42])
    tools = [a.tool_name for a in actions]
    assert tools == ["get_node_detail", "outpaint"]
    assert actions[1].params["node_id"] == 42


def test_plan_upscale_needs_selection():
    actions = plan("超分", {"nodes": [], "edges": []}, [])
    assert actions[0].tool_name == "get_canvas_summary"


def test_plan_extract_frames_with_selected():
    actions = plan("抽帧", {"nodes": [], "edges": []}, [9])
    assert [a.tool_name for a in actions] == ["get_node_detail", "extract_frames"]


def test_outpaint_registered():
    assert "outpaint" in TOOLS
    assert TOOLS["outpaint"].risk_level == "high"


def test_derive_and_operate_creates_connects_submits():
    calls: list[tuple] = []

    def fake_selected(canvas_id, user_id, node_ids=None, **ctx):
        return {
            "selectedNodes": [{
                "id": 10,
                "type": "image",
                "x": 100,
                "y": 200,
                "params": {"lastOutputUrl": "http://src.jpg"},
                "output": {"url": "http://src.jpg"},
                "prompt": "源图",
            }],
            "detail": True,
        }

    def fake_create(canvas_id, user_id, nodes=None, **ctx):
        calls.append(("create", nodes))
        return {"createdNodes": [{"id": 99, "type": "image"}], "count": 1}

    def fake_connect(canvas_id, user_id, edges=None, **ctx):
        calls.append(("connect", edges))
        return {"createdEdges": [{"id": 1}], "count": 1}

    def fake_submit_op(canvas_id, user_id, node_id, model_type, operation, model_params=None,
                       estimated_cost=10, **ctx):
        calls.append(("submit", node_id, operation, model_params))
        return {"ack": True, "task_id": "t1", "status": "queued", "node_id": node_id}

    with (
        patch("agent.tools.registry._get_selected_nodes", fake_selected),
        patch("agent.tools.registry._create_nodes", fake_create),
        patch("agent.tools.registry._connect_nodes", fake_connect),
        patch("agent.tools.registry._submit_media_operation", fake_submit_op),
    ):
        out = _derive_and_operate(
            1,
            2,
            source_node_id=10,
            derived_type="image",
            operation="扩图",
            submit_model_type="image",
            title="扩图",
            prompt="扩展边缘",
            estimated_cost=12,
        )

    assert out["derived"] is True
    assert out["derivedNodeId"] == 99
    assert out["sourceNodeId"] == 10
    assert calls[0][0] == "create"
    assert calls[0][1][0]["type"] == "image"
    assert calls[1][0] == "connect"
    assert calls[1][1][0]["sourceNodeId"] == 10
    assert calls[1][1][0]["targetNodeId"] == 99
    assert calls[2][0] == "submit"
    assert calls[2][1] == 99
    assert calls[2][2] == "扩图"
    assert "http://src.jpg" in (calls[2][3] or {}).get("referenceUrls", [])


def test_derive_inplace_skips_create():
    with patch("agent.tools.registry._submit_media_operation") as submit:
        submit.return_value = {"ack": True, "status": "queued"}
        out = _derive_and_operate(
            1, 2,
            source_node_id=10,
            derived_type="image",
            operation="超分",
            submit_model_type="image",
            title="超分",
            prompt="超分",
            inplace=True,
        )
    assert out["derived"] is False
    submit.assert_called_once()
    # positional: canvas_id, user_id, node_id, model_type, operation, ...
    assert submit.call_args.args[2] == 10
