"""模型解析 + task_status 回复不应被静默吞掉。"""

from __future__ import annotations

from agent.domain.model_defaults import resolve_submit_model
from agent.graph.nodes.reply_builder import reply_builder_node


def test_resolve_text_modality_to_concrete_model():
    assert resolve_submit_model("text") == "agnes-2.5-flash"
    assert resolve_submit_model("text", model_params={"model": "deepseek-v4-flash"}) == "agnes-2.5-flash"
    assert resolve_submit_model("deepseek-chat") == "agnes-2.5-flash"
    assert resolve_submit_model("video").startswith("agnes-video")
    assert resolve_submit_model("image").startswith("agnes-image")


def test_compose_never_resolves_to_seedance():
    assert resolve_submit_model("video", model_params={"operation": "compose"}) == "compose-1.0"
    assert resolve_submit_model("compose") == "compose-1.0"
    assert resolve_submit_model(
        "video",
        model_params={"operation": "compose"},
        node_model_ref="agnes-video-v2.0",
    ) == "compose-1.0"


def test_failed_node_not_auto_submittable():
    from agent.domain.dependency_scheduler import is_node_submittable

    assert not is_node_submittable({"id": 1, "type": "compose", "execStatus": "failed"})
    assert is_node_submittable({"id": 1, "type": "compose", "execStatus": "idle"})


def test_task_status_success_reply_not_silenced_when_downstream_queued():
    state = {
        "reply": "「总脚本」生成完成，产物已写回画布。\n依赖已就绪，已自动提交：提交text生成（分镜）。",
        "reply_type": "task_status",
        "pipeline_stage": "storyboard",
        "suggestions": [],
        "next_actions": ["等待下游生成完成"],
        "events": [],
        "executed_results": [
            {
                "tool": "check_task_status",
                "ok": True,
                "ack": False,
                "data": {"status": "succeeded", "task_id": "1"},
                "task_id": "1",
                "model_type": "text",
            },
            {
                "tool": "submit_generation",
                "ok": True,
                "ack": True,
                "data": {"status": "queued", "task_id": "2"},
                "task_id": "2",
                "model_type": "text",
            },
        ],
        "canvas_context": {},
        "pending_confirm": None,
        "pending_high_risk": [],
    }
    out = reply_builder_node(state)
    assert out["reply"]
    assert "总脚本" in out["reply"]
    assert "后台生成中" not in out["reply"]
    assert any(e.get("type") == "assistant_message" for e in out["events"])


def test_pure_poll_still_silent():
    state = {
        "reply": "",
        "reply_type": "task_status",
        "pipeline_stage": "text_base",
        "suggestions": [],
        "next_actions": [],
        "events": [],
        "executed_results": [
            {
                "tool": "check_task_status",
                "ok": True,
                "ack": True,
                "data": {"status": "running", "task_id": "9"},
                "task_id": "9",
            },
        ],
        "canvas_context": {},
        "pending_confirm": None,
        "pending_high_risk": [],
    }
    out = reply_builder_node(state)
    assert out["reply"] == ""
    assert any(e.get("silent") for e in out["events"])
