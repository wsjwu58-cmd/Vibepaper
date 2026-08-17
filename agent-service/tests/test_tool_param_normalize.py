"""工具参数归一化：兼容 LLM 扁平/驼峰字段。"""

from agent.tools.registry import TOOLS, normalize_tool_params


def test_normalize_load_skill_aliases():
    assert normalize_tool_params("load_skill", {"skillKey": "vertical-short-drama"})["skill_key"] == "vertical-short-drama"
    assert normalize_tool_params("load_skill", {"name": "六格漫画"})["skill_key"] == "六格漫画"
    assert normalize_tool_params("load_skill", {})["skill_key"] == ""


def test_normalize_update_node_config_flattens_prompt():
    out = normalize_tool_params(
        "update_node_config",
        {"nodeId": 42, "prompt": "猫抓老鼠简报", "title": "项目简报"},
    )
    assert out["node_id"] == 42
    assert out["params"]["prompt"] == "猫抓老鼠简报"
    assert out["params"]["title"] == "项目简报"


def test_load_skill_accepts_missing_key_gracefully():
    out = TOOLS["load_skill"].fn(user_id=1, canvas_id=1)
    assert out.get("error_code") == "INVALID_INPUT"


def test_load_skill_with_normalized_params():
    params = normalize_tool_params("load_skill", {"skillKey": "vertical-short-drama"})
    out = TOOLS["load_skill"].fn(user_id=1, canvas_id=1, **params)
    assert "error" not in out
    assert out.get("skill_key") or out.get("loaded_keys")


def test_update_node_config_requires_node_but_accepts_empty_params(monkeypatch):
    calls = {}

    def fake_put(url, headers=None, json=None, timeout=None, trust_env=None):
        calls["json"] = json

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

        return R()

    import agent.tools.registry as reg

    monkeypatch.setattr(reg.httpx, "put", fake_put)
    params = normalize_tool_params("update_node_config", {"node_id": 7, "prompt": "hello"})
    out = TOOLS["update_node_config"].fn(canvas_id=1, user_id=1, **params)
    assert out.get("ok") is True
    assert calls["json"]["prompt"] == "hello"
