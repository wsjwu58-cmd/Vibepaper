"""Skill playbook：选中参考接入视觉/文本编译；三联图落三节点；首尾帧推断。"""

from __future__ import annotations

from agent.agent.planner import _infer_node_type, _plan_create_media
from agent.domain.creative_planner import compile_execution_plan
from agent.tools.registry import _collect_input_references


def _tools(plan) -> list[str]:
    return [(s.payload or {}).get("tool") for s in plan.steps]


def test_film_poster_with_selected_connects_reference():
    plan = compile_execution_plan(
        "根据这张参考图做一张竖版电影海报",
        intent_name="workflow_orchestration",
        requested_skill="电影海报",
        creative={"script_prompt": "赤壁：火焰江面，大字片名"},
        canvas_context={
            "selectedNodes": [{"id": 42, "type": "image", "x": 10, "y": 20}],
            "nodes": [{"id": 42, "type": "image", "x": 10, "y": 20}],
        },
        selected_nodes=[42],
    )
    assert plan.workflow == "film-poster"
    assert "connect_nodes" in _tools(plan)
    connect = next(s for s in plan.steps if (s.payload or {}).get("tool") == "connect_nodes")
    edge = (connect.payload or {})["params"]["edges"][0]
    assert edge["sourceNodeId"] == 42
    assert edge["targetNodeId"] == "$created[0]"
    create = next(s for s in plan.steps if (s.payload or {}).get("tool") == "create_nodes")
    node = (create.payload or {})["params"]["nodes"][0]
    assert node["x"] == 310  # 10 + 300


def test_cinematic_triptych_creates_three_images():
    plan = compile_execution_plan(
        "做一组电影感三联图，雨夜街头",
        intent_name="workflow_orchestration",
        requested_skill="电影感三联图",
        creative={
            "shots": [
                {"keyframe_prompt": "远景雨夜"},
                {"keyframe_prompt": "中景行人"},
                {"keyframe_prompt": "近景灯牌"},
            ],
        },
    )
    assert plan.workflow == "cinematic-triptych"
    create = next(s for s in plan.steps if (s.payload or {}).get("tool") == "create_nodes")
    nodes = (create.payload or {})["params"]["nodes"]
    assert len(nodes) == 3
    assert all(n["type"] == "image" for n in nodes)
    submits = [s for s in plan.steps if (s.payload or {}).get("tool") == "submit_generation"]
    assert len(submits) == 3
    assert [s.payload["params"]["node_id"] for s in submits] == [
        "$created[0]", "$created[1]", "$created[2]",
    ]


def test_text_chain_with_selected_connects_to_image_node():
    plan = compile_execution_plan(
        "根据选中角色卡写分镜清单",
        intent_name="workflow_orchestration",
        requested_skill="分镜与镜头清单",
        creative={
            "script_prompt": "剧本大纲",
            "storyboard_prompt": "分镜表",
        },
        canvas_context={
            "selectedNodes": [{"id": 8, "type": "text", "prompt": "角色卡"}],
            "nodes": [{"id": 8, "type": "text"}],
        },
        selected_nodes=[8],
    )
    assert plan.workflow == "storyboard-shot-list"
    assert "connect_nodes" in _tools(plan)
    # 至少有一条边从选中 8 指出
    sel_edges = []
    for s in plan.steps:
        if (s.payload or {}).get("tool") != "connect_nodes":
            continue
        for e in (s.payload or {}).get("params", {}).get("edges") or []:
            if e.get("sourceNodeId") == 8:
                sel_edges.append(e)
    assert sel_edges


def test_shouwei_frame_infers_video():
    assert _infer_node_type("用这两张图做首尾帧") == "video"
    assert _infer_node_type("首帧到尾帧过渡") == "video"


def test_plan_create_media_shouwei_prefers_dual_images():
    canvas = {
        "selectedNodes": [
            {"id": 3, "type": "text", "x": 0, "y": 0},
            {"id": 1, "type": "image", "x": 0, "y": 0},
            {"id": 2, "type": "image", "x": 100, "y": 0},
        ],
    }
    actions = _plan_create_media("用这两张图做首尾帧", [3, 1, 2], canvas)
    connect = next(a for a in actions if a.tool_name == "connect_nodes")
    srcs = [e["sourceNodeId"] for e in connect.params["edges"]]
    assert srcs[:2] == [1, 2]
    assert actions[-1].params["model_type"] == "video"


def test_collect_input_references_orders_frames_by_edge_id(monkeypatch):
    detail = {
        "nodes": [
            {"id": 1, "type": "image", "output": {"url": "https://a/first.png"}},
            {"id": 2, "type": "image", "output": {"url": "https://a/last.png"}},
            {"id": 9, "type": "video", "params": {}},
        ],
        "edges": [
            # 故意乱序：尾帧边 id 更小
            {"id": 20, "sourceNodeId": 2, "targetNodeId": 9, "dependencyType": "input"},
            {"id": 10, "sourceNodeId": 1, "targetNodeId": 9, "dependencyType": "input"},
        ],
    }

    class _Resp:
        status_code = 200

        def json(self):
            return detail

    monkeypatch.setattr(
        "agent.tools.registry.httpx.get",
        lambda *a, **k: _Resp(),
    )
    monkeypatch.setattr(
        "agent.tools.registry._node_media_url",
        lambda n: (n.get("output") or {}).get("url"),
    )
    refs = _collect_input_references(1, 1, 9)
    assert refs["firstFrameUrl"] == "https://a/first.png"
    assert refs["lastFrameUrl"] == "https://a/last.png"
