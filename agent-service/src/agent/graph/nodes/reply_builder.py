"""reply_builder：汇总结构化回复。"""

from __future__ import annotations

from ..state import AgentState

TOOL_LABELS = {
    "get_canvas_summary": "读取画布",
    "get_selected_nodes": "读取选中节点",
    "get_node_detail": "读取节点详情",
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
    "extract_frames": "抽帧",
    "trim_clip": "剪辑",
    "upscale": "超分",
    "outpaint": "扩图",
    "compose_final": "合成成片",
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
    """收集执行记录步骤：整体 thinking → 推理过程；plan/result → 操作步骤。"""
    steps: list[dict] = []
    idx = 0
    for ev in state.get("events") or []:
        ev_type = ev.get("type")
        if ev_type in ("thinking", "reflection"):
            content = str(ev.get("content") or ev.get("note") or "").strip()
            if not content:
                continue
            steps.append({
                "id": f"reason-{idx}",
                "kind": "reasoning",
                "label": "推理过程",
                "summary": content[:2000],
            })
            idx += 1
        elif ev_type == "plan_step":
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
        elif ev_type == "action_result":
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
    return _dedupe_steps(steps)


def _infer_next_actions_from_results(state: AgentState) -> list[str]:
    """只透传规划阶段给出的 next_actions；不再按模型类型/阶段硬编码词表。"""
    return list(state.get("next_actions") or [])[:5]

def _build_reply_from_results(state: AgentState) -> str:
    results = state.get("executed_results") or []
    pending = state.get("pending_high_risk") or []
    lines: list[str] = []

    preset = (state.get("reply") or "").strip()
    from ...domain.turn_policy import is_process_narration, silence_process_reply

    if preset and is_process_narration(preset) and not state.get("needs_user_input"):
        preset = ""
    # task_status 的成功/失败文案也是正式回复，不能丢
    if preset:
        lines.append(preset)

    submitted = [
        r for r in results
        if r.get("ack") and r.get("task_id") and r.get("tool") == "submit_generation"
    ]
    created = [r for r in results if r.get("ok") and r.get("tool") == "create_nodes"]
    failed = [r for r in results if not r.get("ok") and r.get("tool") != "check_task_status"]

    if created and not preset:
        count = sum(len((r.get("data") or {}).get("createdNodes") or []) or 1 for r in created)
        lines.append(f"✅ 已在画布创建 {count} 个节点并建立连线")

    # 提交中的话术不进对话气泡（会在每次 clock 唤醒时刷屏）。
    # 唤醒完成文案在 preset；workflow_notes 只在首次创建节点时带一条。
    if created and not preset:
        for r in submitted:
            for note in (r.get("workflow_notes") or (r.get("data") or {}).get("workflow_notes") or []):
                if note:
                    lines.append(f"· {note}")
                    break

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
        if state.get("needs_user_input"):
            lines.append(silence_process_reply(state.get("reply") or "", keep_if_genuine_ask=True) or "还缺一条关键信息才能继续。")
        elif created or submitted:
            pass
        elif (state.get("reply_type") or "") in ("directions", "summary", "copy") and (state.get("reply") or "").strip():
            # 讨论/建议态：preset 已被 is_process_narration 误杀时，仍应用 state.reply
            lines.append((state.get("reply") or "").strip())
        else:
            # 无结果且无提问：保持静默，避免「指令已理解」假完成
            return ""

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
            return {
                "reply": "",
                "events": [{
                    "type": "task_status",
                    "silent": True,
                    "data": (state.get("executed_results") or [{}])[0].get("data") or {},
                }],
            }

    reply = _build_reply_from_results(state)
    # 下一步建议由前端 AgentNextActions 可点击渲染，不在正文重复拼一段文本

    out: dict = {
        "reply": reply,
        "next_actions": next_actions,
    }
    if reply.strip():
        out["events"] = [{
            "type": "assistant_message",
            "content": reply,
            "replyType": reply_type,
            "pipelineStage": stage,
            "suggestions": suggestions,
            "nextActions": next_actions,
            "executionSteps": execution_steps,
            "staleNodes": (state.get("canvas_context") or {}).get("staleNodes") or [],
            "requiresConfirmation": bool(state.get("pending_confirm") or state.get("pending_high_risk")),
        }]
    return out
