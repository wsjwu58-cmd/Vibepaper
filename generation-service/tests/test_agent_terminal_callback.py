import pytest
from types import SimpleNamespace

from generation.services.agent_terminal_callback import build_agent_terminal_callback


def test_terminal_callback_is_task_scoped_and_fail_closed_in_production(monkeypatch):
    task = SimpleNamespace(id=55, canvas_id=1, node_id=2, user_id=3, error_code=None, model_type="image", actual_cost=4)
    request = build_agent_terminal_callback("http://agent", task, "succeeded", "production", "internal-secret")
    assert request["headers"]["X-Internal-Service-Token"] == "internal-secret"
    assert "sessionId" not in request["json"]
    assert request["json"]["task_id"] == "55"
    assert request["json"]["node_id"] == "2"
    assert request["json"]["canvas_id"] == "1"
    assert request["json"]["user_id"] == "3"

    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_TOKEN_MISSING"):
        build_agent_terminal_callback("http://agent", task, "succeeded", "production", "")
