"""planner：结构化 LLM 规划 + P1 专用路径 + 规则 fallback。"""

from __future__ import annotations

from ...agent.persona import PAPER_AGENT_INSTRUCTIONS
from ...agent.planner import (
    PlanResult,
    _paper_fallback_reply,
    classify_intent,
    detect_pipeline_stage,
    llm_plan_structured,
    llm_suggest_next_actions,
    plan,
)
from ...core.config import settings
from ...domain.pipeline import plan_advance_pipeline, plan_reregenerate_stale
from ...domain.precedence import classify_stance, filter_actions_for_stance
from ..state import AgentState, PlannedActionDict


def _filter_replan_actions(state: AgentState, planned: list[PlannedActionDict]) -> list[PlannedActionDict]:
    """反思重规划时跳过已成功步骤，避免执行记录重复。"""
    if not state.get("reflection_note"):
        return planned
    done = {
        (r.get("tool"), r.get("summary"))
        for r in (state.get("executed_results") or [])
        if r.get("ok")
    }
    if not done:
        return planned
    filtered = [a for a in planned if (a["tool_name"], a.get("summary")) not in done]
    return filtered if filtered else planned


def planner_node(state: AgentState) -> dict:
    content = state["user_content"]
    ctx = state.get("canvas_context") or {}
    selected = state.get("selected_nodes") or []
    intent = classify_intent(content)
    stance = classify_stance(content, intent)

    # 讨论态：不走编排/推进等写路径，避免「问方案却开始搭节点」
    if stance == "discuss" and intent in (
        "advance_pipeline", "reregenerate_stale", "orchestrate_workflow",
        "create", "generate", "delete", "update", "connect", "layout", "model",
    ):
        intent = "general"

    # P1 专用路径：优先于 LLM（仅指令态）
    if stance == "instruct" and intent == "advance_pipeline":
        result = plan_advance_pipeline(ctx, selected)
    elif stance == "instruct" and intent == "reregenerate_stale":
        result = plan_reregenerate_stale(ctx)
    elif stance == "instruct" and intent == "orchestrate_workflow":
        from ...domain.workflow_orchestrator import plan_workflow_orchestration
        result = plan_workflow_orchestration(content, ctx, selected)
    elif settings.llm_api_key:
        result = llm_plan_structured(
            content=content,
            canvas_context=ctx,
            selected_nodes=selected,
            recent_messages=state.get("recent_messages"),
            skill_instructions=state.get("skill_instructions") or PAPER_AGENT_INSTRUCTIONS,
            api_key=settings.llm_api_key,
            base_url=settings.normalized_llm_base_url(),
            model=settings.llm_model,
            long_term_prefs=state.get("long_term_prefs"),
        )
    else:
        # Paper 意图无 LLM 时明确降级
        if intent in ("summarize", "copy", "directions") or stance == "discuss":
            result = _paper_fallback_reply(
                intent if intent in ("summarize", "copy", "directions") else "directions",
                ctx,
            )
        else:
            actions = plan(content, ctx, selected)
            result = PlanResult(
                actions=actions,
                reply="",
                reply_type="general",
                pipeline_stage=detect_pipeline_stage(ctx),
                llm_available=False,
            )

    # 讨论态：剥掉写/执行动作，只保留只读
    if stance == "discuss":
        result.actions = filter_actions_for_stance(result.actions, "discuss")

    # 规则路径或 LLM 未给出建议时：有 Key 则让模型按上下文自写，禁止场景词表硬编码
    if not result.next_actions and settings.llm_api_key:
        result.next_actions = llm_suggest_next_actions(
            content=content,
            reply=result.reply or "",
            pipeline_stage=result.pipeline_stage or detect_pipeline_stage(ctx),
            actions=result.actions,
            canvas_context=ctx,
            api_key=settings.llm_api_key,
            base_url=settings.normalized_llm_base_url(),
            model=settings.llm_model,
        )

    planned: list[PlannedActionDict] = []
    for a in result.actions:
        params = dict(a.params or {})
        # 删除/生成等操作自动注入选中节点，避免 LLM 漏传
        if a.tool_name == "delete_nodes" and not params.get("node_ids") and selected:
            params["node_ids"] = selected
        if a.tool_name in ("submit_generation", "update_node_config", "change_model", "replace_output",
                           "extract_frames", "trim_clip", "upscale", "outpaint", "compose_final", "capture_3d_scene"):
            if not params.get("node_id") and not params.get("nodeId") and selected:
                params["node_id"] = selected[0]
        planned.append({
            "tool_name": a.tool_name,
            "params": params,
            "summary": a.summary,
            "reasoning": a.reasoning or "",
            "status": "pending",
        })

    planned = _filter_replan_actions(state, planned)
    if stance == "discuss":
        planned = filter_actions_for_stance(planned, "discuss")

    events: list[dict] = []
    note = state.get("reflection_note")
    if note:
        events.append({"type": "reflection", "note": note})
    if result.thinking:
        events.append({"type": "thinking", "content": result.thinking})
    events.append({"type": "stance", "stance": stance, "intent": intent})
    for a in planned:
        events.append({
            "type": "plan_step",
            "tool": a["tool_name"],
            "summary": a.get("summary"),
            "reasoning": a.get("reasoning") or "",
        })

    return {
        "planned_actions": planned,
        "intent_type": intent,
        "reply": result.reply,
        "reply_type": result.reply_type,
        "pipeline_stage": result.pipeline_stage,
        "suggestions": result.suggestions,
        "next_actions": result.next_actions,
        "events": events,
    }
