"""选中参考 → 新建下游 → 连线 → 提交；节点完整读取。"""

from __future__ import annotations

from agent.agent.planner import _plan_create_media, _plan_image_to_video, plan
from agent.tools.registry import _attach_graph_neighbors


def test_plan_create_media_with_selected_connects_and_submits_created():
    actions = _plan_create_media("根据这张图生成一张赛博朋克海报", [101])
    tools = [a.tool_name for a in actions]
    assert tools == [
        "get_selected_nodes",
        "create_nodes",
        "connect_nodes",
        "submit_generation",
    ]
    connect = next(a for a in actions if a.tool_name == "connect_nodes")
    edge = connect.params["edges"][0]
    assert edge["sourceNodeId"] == 101
    assert edge["targetNodeId"] == "$created[0]"
    assert edge["dependencyType"] == "input"
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["node_id"] == "$created[0]"
    assert submit.params["model_type"] == "image"


def test_plan_create_media_without_selected_submits_created():
    actions = _plan_create_media("生成一只橘猫图片", [])
    tools = [a.tool_name for a in actions]
    assert "create_nodes" in tools
    assert "connect_nodes" not in tools
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["node_id"] == "$created[0]"


def test_plan_image_to_video_uses_created_placeholders():
    canvas = {
        "nodes": [{
            "id": 7,
            "type": "image",
            "execStatus": "succeeded",
            "status": "succeeded",
        }],
        "edges": [],
    }
    actions = _plan_image_to_video("把这张图做成视频", [7], canvas)
    connect = next(a for a in actions if a.tool_name == "connect_nodes")
    assert connect.params["edges"][0]["targetNodeId"] == "$created[0]"
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["node_id"] == "$created[0]"
    assert submit.params["model_type"] == "video"


def test_plan_generate_with_selected_derives_new_node():
    actions = plan("生成一张海报", {"nodes": [], "edges": []}, [55])
    tools = [a.tool_name for a in actions]
    assert "create_nodes" in tools
    assert "connect_nodes" in tools
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["node_id"] == "$created[0]"


def test_plan_inplace_regenerate_on_selected():
    actions = plan("重新生成当前节点", {"nodes": [], "edges": []}, [55])
    tools = [a.tool_name for a in actions]
    assert "get_node_detail" in tools
    assert "create_nodes" not in tools
    submit = next(a for a in actions if a.tool_name == "submit_generation")
    assert submit.params["node_id"] == 55


def test_attach_graph_neighbors_includes_full_fields():
    nodes = {
        1: {
            "id": 1,
            "type": "text",
            "prompt": "角色卡全文足够长不应被截断" * 3,
            "params": {"prompt": "角色卡全文足够长不应被截断" * 3, "title": "角色卡", "model": "agnes"},
            "output": {"text": "输出正文"},
            "status": "succeeded",
            "execStatus": "succeeded",
        },
        2: {
            "id": 2,
            "type": "image",
            "prompt": "形象图",
            "params": {"title": "形象"},
            "status": "idle",
        },
    }
    edges = [{
        "id": 9,
        "sourceNodeId": 1,
        "targetNodeId": 2,
        "dependencyType": "input",
        "valid": True,
    }]
    detail = _attach_graph_neighbors(nodes[2], nodes, edges)
    assert detail["prompt"] == "形象图"
    assert detail["params"]["title"] == "形象"
    assert len(detail["upstream"]) == 1
    assert detail["upstream"][0]["id"] == 1
    assert detail["incomingEdges"][0]["dependencyType"] == "input"
    assert detail["upstream"][0]["prompt"]  # neighbor brief keeps prompt snippet
