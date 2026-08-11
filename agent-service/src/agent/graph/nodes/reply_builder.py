"""reply_builder：汇总结构化回复。"""

from __future__ import annotations

from ..state import AgentState

TOOL_LABELS = {
    "get_canvas_summary": "读取画布",
    "get_selected_nodes": "读取选中节点",
    "list_models": "查询模型",
    "search_assets": "查询资源",
    "create_nodes": "编辑画布",
    "connect_nodes": "编辑画布",
    "layout_nodes": "整理画布",
    "update_node_config": "修改节点",
    "delete_nodes": "删除节点",
    "change_model": "切换模型",
    "replace_output": "覆盖输出",
    "submit_generation": "提交生成",
    "check_task_status": "查询任务",
}


def _tool_label(tool: str | None) -> str:
    if not tool:
        return "操作"
    return TOOL_LABELS.get(tool, tool)


def _dedupe_steps(steps: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for s in steps:
        key = (s.get("kind"), s.get("tool"), s.get("summary"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _collect_execution_steps(state: AgentState) -> list[dict]:
    steps: list[dict] = []
    idx = 0
    for ev in state.get("events") or []:
        if ev.get("type") == "plan_step":
            tool = ev.get("tool")
            steps.append({
                "id": f"plan-{idx}",
                "kind": "plan",
                "tool": tool,
                "label": _tool_label(tool),
                "summary": ev.get("summary") or _tool_label(tool),
                "reasoning": str(ev.get("reasoning") or "")[:400],
            })
            idx += 1
        elif ev.get("type") == "action_result":
            tool = ev.get("tool")
            ok = bool(ev.get("ok"))
            data = ev.get("data") or {}
            detail = data.get("error") if not ok else None
            if ok and tool == "submit_generation":
                detail = "已受理，排队生成中"
            steps.append({
                "id": f"result-{idx}",
                "kind": "result",
                "tool": tool,
                "label": _tool_label(tool),
                "summary": f"{_tool_label(tool)} {'完成' if ok else '失败'}",
                "ok": ok,
                "detail": detail,
            })
            idx += 1
        # thinking / reflection 不单独成「推理过程」块（图二）；
        # 理由落在 plan_step.reasoning → 前端「为什么这么做」（图一）
    return _dedupe_steps(steps)


def _infer_next_actions_from_results(state: AgentState) -> list[str]:
    existing = list(state.get("next_actions") or [])
    if existing:
        return existing[:5]
    hints: list[str] = []
    for r in state.get("executed_results") or []:
        if r.get("ack"):
            mt = r.get("model_type") or ""
            if mt == "image":
                hints = ["图生视频", "换风格重做", "微调 Prompt 再生成"]
            elif mt == "video":
                hints = ["换运镜重做", "抽帧 / 裁剪", "接续剧情"]
            elif mt == "text":
                hints = ["生成配图", "延展三个方向", "改写文案"]
        elif r.get("ok") and r.get("tool") == "create_nodes":
            hints = hints or ["提交生成", "调整节点布局"]
    stage = state.get("pipeline_stage") or ""
    if not hints and stage in ("visual_anchor", "dynamic_gen"):
        hints = ["图生视频", "添加配音", "整理画布"]
    return hints[:5] or ["梳理画布", "给我三个方向"]


def _build_reply_from_results(state: AgentState) -> str:
    results = state.get("executed_results") or []
    pending = state.get("pending_high_risk") or []
    lines: list[str] = []

    preset = (state.get("reply") or "").strip()
    # task_status 的成功/失败文案也是正式回复，不能丢
    if preset:
        lines.append(preset)

    submitted = [r for r in results if r.get("ack") and r.get("task_id")]
    created = [r for r in results if r.get("ok") and r.get("tool") == "create_nodes"]
    failed = [r for r in results if not r.get("ok")]

    if created and not preset:
        count = sum(len((r.get("data") or {}).get("createdNodes") or []) or 1 for r in created)
        lines.append(f"✅ 已在画布创建 {count} 个节点并建立连线")

    for r in submitted:
        mt = r.get("model_type") or "生成"
        lines.append(
            f"⏳ {mt} 任务已提交，后台生成中；"
            f"依赖就绪的下游节点会自动开始，完成后我来通知你"
        )

    for r in failed:
        err = (r.get("data") or {}).get("error", "未知错误")
        lines.append(f"❌ {_tool_label(r.get('tool'))} 失败：{err}")

    if (pending or state.get("pending_confirm")) and not submitted:
        confirm = state.get("pending_confirm") or {}
        if confirm.get("dialogConfirm"):
            from ..confirm_helpers import build_dialog_confirm_prompt
            fake_action = {
                "tool_name": confirm.get("tool"),
                "summary": confirm.get("summary"),
                "params": {"estimated_cost": confirm.get("estimatedCost") or 0},
            }
            lines.append(build_dialog_confirm_prompt(
                fake_action, chain_cost=int(confirm.get("chainEstimatedCost") or 0),
            ))
        else:
            lines.append("⏸ 有操作待你确认后才会改画布或扣费")

    if not lines:
        lines.append("已理解指令。可以继续描述创作目标，或让我梳理画布 / 写文案 / 延展方向。")

    return "\n".join(lines)


def reply_builder_node(state: AgentState) -> dict:
    reply_type = state.get("reply_type") or "general"
    stage = state.get("pipeline_stage") or "text_base"
    suggestions = state.get("suggestions") or []
    next_actions = _infer_next_actions_from_results(state)
    execution_steps = _collect_execution_steps(state)

    # 纯轮询（尚无终态文案）才静默；已有成功/失败 reply 或下游新提交时必须出声
    if reply_type == "task_status":
        preset = (state.get("reply") or "").strip()
        statuses = [
            str((r.get("data") or {}).get("status") or "")
            for r in (state.get("executed_results") or [])
        ]
        has_terminal = any(
            s in ("succeeded", "failed", "expired", "cancelled", "settlement_error")
            for s in statuses
        )
        only_inflight = statuses and all(s in ("queued", "running", "") for s in statuses)
        if only_inflight and not has_terminal and not preset:
            events = list(state.get("events") or [])
            events.append({
                "type": "task_status",
                "silent": True,
                "data": (state.get("executed_results") or [{}])[0].get("data") or {},
            })
            return {"reply": "", "events": events}

    reply = _build_reply_from_results(state)
    # 下一步建议由前端 AgentNextActions 可点击渲染，不在正文重复拼一段文本

    events = list(state.get("events") or [])
    if reply.strip():
        events.append({
            "type": "assistant_message",
            "content": reply,
            "replyType": reply_type,
            "pipelineStage": stage,
            "suggestions": suggestions,
            "nextActions": next_actions,
            "executionSteps": execution_steps,
            "staleNodes": (state.get("canvas_context") or {}).get("staleNodes") or [],
            "requiresConfirmation": bool(state.get("pending_confirm") or state.get("pending_high_risk")),
        })
    return {
        "reply": reply,
        "next_actions": next_actions,
        "events": events,
    }
