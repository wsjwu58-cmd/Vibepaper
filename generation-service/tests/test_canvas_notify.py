"""生成终态回写画布节点 status/execStatus + Agent resume。"""

from types import SimpleNamespace

from generation.services.task_service import TaskService


def test_notify_canvas_writes_succeeded_exec_status(monkeypatch):
    calls = []
    posts = []

    def fake_put(url, headers=None, json=None, timeout=None, trust_env=None):
        calls.append({"url": url, "json": json, "headers": headers})

        class R:
            status_code = 200

        return R()

    def fake_post(url, json=None, timeout=None, trust_env=None):
        posts.append({"url": url, "json": json})

        class R:
            status_code = 200

        return R()

    monkeypatch.setattr("generation.services.task_service.httpx.put", fake_put)
    monkeypatch.setattr("generation.services.task_service.httpx.post", fake_post)
    task = SimpleNamespace(
        id=99, canvas_id=11, node_id=22, user_id=33, source="agent",
        error_code=None, model_type="image",
    )
    out = SimpleNamespace(url="http://x/a.png", meta={})
    TaskService().notify_canvas_node(task, "succeeded", [out])
    assert calls
    body = calls[0]["json"]
    assert body["status"] == "succeeded"
    assert body["execStatus"] == "succeeded"
    assert "params" not in body
    assert body["output"]["url"] == "http://x/a.png"
    assert calls[0]["headers"]["X-User-Id"] == "33"
    assert "/canvases/11/nodes/22" in calls[0]["url"]
    assert posts and "/internal/agent/resume" in posts[0]["url"]


def test_notify_canvas_skips_without_ids(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "generation.services.task_service.httpx.put",
        lambda *a, **k: calls.append(1),
    )
    monkeypatch.setattr(
        "generation.services.task_service.httpx.post",
        lambda *a, **k: calls.append(2),
    )
    TaskService().notify_canvas_node(SimpleNamespace(canvas_id=None, node_id=1, user_id=1), "succeeded")
    assert calls == []


def test_notify_agent_resume_on_terminal(monkeypatch):
    posts = []

    class FakeResp:
        status_code = 200

    def fake_post(url, json=None, timeout=None, trust_env=None):
        posts.append({"url": url, "json": json})
        return FakeResp()

    monkeypatch.setattr("generation.services.task_service.httpx.post", fake_post)
    monkeypatch.setattr("generation.services.task_service.httpx.put", lambda *a, **k: FakeResp())
    task = SimpleNamespace(
        id=55, canvas_id=1, node_id=2, user_id=3, source="agent",
        error_code=None, model_type="image",
    )
    TaskService().notify_canvas_node(task, "succeeded", [])
    assert posts
    assert "/internal/agent/resume" in posts[0]["url"]
    assert posts[0]["json"]["status"] == "succeeded"

    posts.clear()
    TaskService().notify_canvas_node(task, "running", [])
    assert posts == []
