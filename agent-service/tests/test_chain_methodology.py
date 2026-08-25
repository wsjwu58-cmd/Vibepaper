"""工作方式链路审计修复的回归测试：

- 整体确认：链路后续自动提交的合计点数预估与话术
- stale 重跑：沿用节点自身 prompt，不暴露内部 id
- 依赖图布局：上游在左、多输入在右、独立分量在下方
- 异步纪律：失败/过期话术人性化，不暴露 task/node id
- update 意图：不把用户原话原封塞入 prompt
"""

from __future__ import annotations

from agent.agent.planner import plan
from agent.domain.dependency_graph import compute_dependency_layout
from agent.domain.dependency_scheduler import estimate_downstream_cost
from agent.domain.pipeline import plan_reregenerate_stale
from agent.graph.confirm_helpers import build_dialog_confirm_prompt, build_inline_confirm_text
from agent.graph.nodes.check_task_status_node import _humanize_task_error, _node_title


# ---------- 整体确认（差距 1） ----------

def test_estimate_downstream_cost_sums_submittable_descendants():
    ctx = {
        "nodes": [
            {"id": 1, "type": "text", "creativeType": "script", "execStatus": "ready"},
            {"id": 2, "type": "text", "creativeType": "shot", "execStatus": "idle"},
            {"id": 3, "type": "image", "creativeType": "keyframe", "execStatus": "idle"},
            {"id": 4, "type": "image", "creativeType": "keyframe", "execStatus": "ready"},
        ],
        "edges": [
            {"source": 1, "target": 2, "dependencyType": "input"},
            {"source": 2, "target": 3, "dependencyType": "input"},
            {"source": 1, "target": 4, "dependencyType": "input"},
        ],
    }
    # 下游 = 2(text:8) + 3(image:8)；4 已 ready 不再计入
    assert estimate_downstream_cost(1, ctx) == 16
    # 叶子节点无下游
    assert estimate_downstream_cost(3, ctx) == 0


def test_confirm_prompt_shows_chain_total():
    action = {
        "tool_name": "submit_generation",
        "summary": "提交总脚本生成（依赖链起点）",
        "params": {"estimated_cost": 8},
    }
    text = build_dialog_confirm_prompt(action, chain_cost=137)
    assert "本次预估 8 点" in text
    assert "合计约 145 点" in text
    assert "自动提交" in text

    inline = build_inline_confirm_text(action, accepted=True, chain_cost=137)
    assert "合计约 145 点" in inline

    # 无链路费时保持原话术
    plain = build_dialog_confirm_prompt(action)
    assert "预估 8 点" in plain
    assert "合计" not in plain


def test_short_drama_root_submit_carries_chain_cost():
    from agent.domain.dependency_scheduler import DEFAULT_COST
    from agent.domain.video_task import estimate_video_cost
    from agent.domain.workflow_orchestrator import plan_short_drama_workflow

    result = plan_short_drama_workflow("做一个30秒短剧，3个镜头", None)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    creates = [a for a in result.actions if a.tool_name == "create_nodes"]
    video_params = {}
    for a in creates:
        for n in a.params.get("nodes") or []:
            if n.get("type") == "video":
                video_params = n.get("params") or {}
                break
    per_video = estimate_video_cost(
        str(video_params.get("model") or ""),
        {"duration": video_params.get("duration"), "count": 1},
    )
    # 链路费 = 分镜 + 首帧×3 + 视频×3 + 成片（视频单价随目录/偏好估价）
    expected = (
        DEFAULT_COST["text"]
        + DEFAULT_COST["image"] * 3
        + per_video * 3
        + DEFAULT_COST["compose"]
    )
    assert submits[0].params["chain_estimated_cost"] == expected
    assert "合计约" in result.reply


# ---------- stale 重跑（差距 2） ----------

def test_reregenerate_stale_uses_node_prompt_and_title():
    own_prompt = "黄昏城门外，少女远景，冷色调，电影感构图"
    ctx = {
        "nodes": [
            {
                "id": 9,
                "type": "image",
                "creativeType": "keyframe",
                "prompt": own_prompt,
                "params": {"title": "镜头1首帧"},
                "stale": True,
            },
        ],
        "edges": [],
        "staleNodes": [{"nodeId": 9, "type": "image", "title": "镜头1首帧"}],
    }
    result = plan_reregenerate_stale(ctx)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["model_params"]["prompt"] == own_prompt
    assert submits[0].summary == "重跑「镜头1首帧」"
    assert "节点 9" not in result.reply
    assert result.next_actions == []


def test_reregenerate_stale_compose_uses_compose_final():
    ctx = {
        "nodes": [
            {"id": 5, "type": "compose", "creativeType": "composite",
             "prompt": "按镜头顺序拼接，保持节奏一致", "params": {"title": "成片"}, "stale": True},
        ],
        "edges": [],
    }
    result = plan_reregenerate_stale(ctx)
    tools = [a.tool_name for a in result.actions]
    assert "compose_final" in tools
    assert "submit_generation" not in tools


# ---------- 依赖图布局（差距 3） ----------

def test_dependency_layout_layering_and_components():
    nodes = [
        {"id": 1, "x": 100, "y": 100},
        {"id": 2, "x": 500, "y": 100},
        {"id": 3, "x": 900, "y": 100},
        {"id": 5, "x": 900, "y": 300},
        {"id": 4, "x": 100, "y": 500},  # 独立节点（新行）
    ]
    edges = [
        {"source": 1, "target": 2, "dependencyType": "input"},
        {"source": 2, "target": 3, "dependencyType": "input"},
        {"source": 2, "target": 5, "dependencyType": "input"},
        {"source": 3, "target": 5, "dependencyType": "input"},
    ]
    pos = compute_dependency_layout(nodes, edges)
    # 单源派生放源右侧：x 随层递增
    assert pos[1][0] < pos[2][0] < pos[3][0]
    # 多输入放输入组包围盒右侧
    assert pos[5][0] > pos[3][0]
    # 新行放内容下方
    assert pos[4][1] > pos[1][1]
    # 同层同 x 不重叠
    assert len({p for p in pos.values()}) == len(pos)


# ---------- 异步纪律话术（差距 5/7） ----------

def test_humanize_task_error_maps_codes():
    assert _humanize_task_error({"error_code": "INSUFFICIENT_POINTS"}) == "点数不足，请先充值"
    assert _humanize_task_error({"errorCode": "CONTENT_BLOCKED"}) == "内容未通过安全审核，建议调整画面描述"
    assert _humanize_task_error({"error": "模型炸了"}) == "模型炸了"
    assert _humanize_task_error({}) == "原因未知"


def test_node_title_never_exposes_id():
    ctx = {"nodes": [{"id": 9, "params": {"title": "镜头1首帧"}}]}
    assert _node_title(ctx, 9) == "镜头1首帧"
    fallback = _node_title({}, 9)
    assert "9" not in fallback


# ---------- update 原话禁令（差距 6） ----------

def test_update_intent_strips_instruction_prefix():
    actions = plan("把镜头1的prompt改成黄昏时分的城门", {"nodes": [], "edges": []}, [9])
    assert actions[0].tool_name == "update_node_config"
    prompt = actions[0].params["params"]["prompt"]
    assert prompt == "黄昏时分的城门"
    assert "把" not in prompt and "改成" not in prompt


# ---------- $created[N] 占位符解析（确认后二次执行） ----------

def test_resolve_created_placeholder():
    from agent.graph.nodes.executor import _resolve_node_ref

    assert _resolve_node_ref("$created[0]", [101, 202], None) == 101
    assert _resolve_node_ref("$created[1]", [101, 202], None) == 202
    assert _resolve_node_ref("$created[-1]", [101, 202], None) == 202
    assert _resolve_node_ref(None, [101], 101) == 101
    # 越界回退 last
    assert _resolve_node_ref("$created[9]", [101], 101) == 101


def test_submit_rejects_unresolved_placeholder():
    from agent.tools.registry import _submit_generation

    out = _submit_generation(
        canvas_id=1, user_id=1, node_id="$created[0]",
        model_type="image", model_params={}, estimated_cost=8,
    )
    assert "error" in out
    assert out.get("error_code") == "INVALID_INPUT"
    assert "占位符" in out["error"] or "节点" in out["error"]


# ---------- 输出形式：推理过程 + 结论总结 + 下一步建议 ----------

def test_rule_paths_carry_reasoning():
    """规则路径的每个动作都带推理说明（创作者语言）。"""
    actions = plan("生成一只穿靴子的橘猫图片", {"nodes": [], "edges": []}, [])
    assert actions
    for a in actions:
        assert a.reasoning, f"{a.tool_name} 缺少 reasoning"


def test_short_drama_has_thinking_and_reasoning():
    from agent.domain.workflow_orchestrator import plan_short_drama_workflow

    result = plan_short_drama_workflow("做一个30秒短剧，3个镜头", None)
    assert result.thinking  # 整体推理非空
    for a in result.actions:
        assert a.reasoning, f"{a.tool_name}（{a.summary}）缺少 reasoning"


def test_reregenerate_stale_has_thinking_and_reasoning():
    ctx = {
        "nodes": [
            {"id": 9, "type": "image", "creativeType": "keyframe",
             "prompt": "黄昏城门外，少女远景，冷色调", "params": {"title": "镜头1首帧"}},
        ],
        "edges": [],
        "staleNodes": [{"nodeId": 9, "type": "image", "title": "镜头1首帧"}],
    }
    result = plan_reregenerate_stale(ctx)
    assert result.thinking
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert submits and all(a.reasoning for a in submits)


def test_reply_builder_collects_thinking_as_reasoning_block():
    """图二样式：thinking → 执行记录「推理过程」；plan_step.reasoning →「为什么这么做」。"""
    from agent.graph.nodes.reply_builder import _collect_execution_steps

    state = {
        "events": [
            {"type": "thinking", "content": "The user wants a full pipeline..."},
            {"type": "plan_step", "tool": "create_nodes", "summary": "创建角色卡",
             "reasoning": "独立成节点，可单独重跑"},
            {"type": "action_result", "tool": "submit_generation", "ok": True, "data": {}},
        ],
    }
    steps = _collect_execution_steps(state)
    kinds = [s["kind"] for s in steps]
    assert kinds == ["reasoning", "plan", "result"]
    assert steps[0]["label"] == "推理过程"
    assert "full pipeline" in steps[0]["summary"]
    assert steps[1]["reasoning"] == "独立成节点，可单独重跑"


def test_exec_reply_has_status_markers_and_next_steps():
    from agent.graph.nodes.reply_builder import _build_reply_from_results

    state = {
        "executed_results": [
            {"tool": "create_nodes", "ok": True, "data": {"createdNodes": [{"id": 1}, {"id": 2}]}},
            {"tool": "submit_generation", "ok": True, "ack": True, "task_id": "t1",
             "model_type": "image", "data": {}},
            {"tool": "submit_generation", "ok": False, "summary": "提交视频生成",
             "data": {"error": "并发任务数达上限"}},
        ],
        "pending_high_risk": [],
        "next_actions": ["推进视频层", "调整角色设定"],
    }
    reply = _build_reply_from_results(state)
    assert "✅" in reply and "2 个节点" in reply
    assert "后台生成中" not in reply
    assert "❌" in reply and "并发任务数达上限" in reply
    assert "task_id" not in reply and "t1" not in reply


def test_reply_builder_does_not_invent_next_actions():
    """执行结果不得按模型类型硬编码下一步建议词表。"""
    from agent.graph.nodes.reply_builder import reply_builder_node

    state = {
        "reply": "已提交",
        "reply_type": "general",
        "pipeline_stage": "visual_anchor",
        "executed_results": [
            {"tool": "submit_generation", "ok": True, "ack": True, "task_id": "t1",
             "model_type": "image", "data": {}},
        ],
        "next_actions": [],
        "events": [],
    }
    out = reply_builder_node(state)
    assert out["next_actions"] == []
    msg = next(e for e in out["events"] if e.get("type") == "assistant_message")
    assert msg.get("nextActions") == []
