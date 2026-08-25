"""LLM JSON 稳健解析。"""

from agent.domain.llm_json import parse_llm_json


def test_parse_plain_object():
    assert parse_llm_json('{"a": 1, "b": "x"}')["a"] == 1


def test_parse_markdown_fence():
    raw = """```json
{"thinking": "ok", "decision": "act", "actions": []}
```"""
    data = parse_llm_json(raw)
    assert data["decision"] == "act"


def test_parse_trailing_comma():
    raw = '{\n  "thinking": "t",\n  "decision": "finish",\n}'
    data = parse_llm_json(raw)
    assert data["decision"] == "finish"


def test_parse_prefix_noise():
    raw = 'Here is the plan:\n{"reply": "hi", "actions": [{"tool": "create_nodes", "params": {}}]}\nThanks'
    data = parse_llm_json(raw)
    assert data["reply"] == "hi"
    assert data["actions"][0]["tool"] == "create_nodes"


def test_parse_chinese_quotes_in_keys_values():
    # 值里中文弯引号经 repair 仍可能失败；至少对象可提取
    raw = '{"thinking":"选“A”推进","decision":"act","actions":[]}'
    data = parse_llm_json(raw)
    assert data["decision"] == "act"


def test_react_json_fail_falls_back_to_workflow(monkeypatch):
    import agent.graph.nodes.react_agent as ra
    from agent.domain.plan_models import PlanStep, StructuredPlan

    def boom(**kwargs):
        raise json.JSONDecodeError("Expecting ',' delimiter", "x", 53)

    import json

    fb = StructuredPlan(
        goal="短剧",
        steps=[PlanStep(id="s1", kind="edit", title="建简报", purpose="落节点",
                        payload={"tool": "create_nodes", "params": {"nodes": [{"type": "text"}]}})],
        reply="开始搭建",
        thinking="兜底",
    )
    monkeypatch.setattr(ra.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(ra, "_call_react_llm", boom)
    monkeypatch.setattr(ra, "_structured_workflow_fallback", lambda state: fb)
    out = ra.react_agent_node({
        "user_content": "创建猫抓老鼠的短剧",
        "intent": {"name": "workflow_orchestration", "wants_execution": True},
        "canvas_context": {"nodeCount": 0},
        "react_step": 0,
        "max_react_steps": 8,
        "selected_skill_keys": [],
        "observations": [],
        "executed_results": [],
        "recent_messages": [],
        "skill_instructions": "",
    })
    assert out["validation_route"] == "execute"
    assert "模型输出异常" in (out["events"][0].get("content") or "") or out.get("reply")
