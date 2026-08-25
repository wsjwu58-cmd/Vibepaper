"""四段编排节点：ingest → intent → skill/plan/validate →（桥接 risk/executor）。"""

from __future__ import annotations

from typing import Any

from ...agent.persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS
from ...core.config import settings
from ...domain.creative_planner import build_structured_plan, steps_to_planned_actions
from ...domain.intent_classifier import classify_intent_hybrid, route_intent_name
from ...domain.plan_models import (
    intent_from_dict,
    is_task_complete,
    plan_from_dict,
    plan_to_dict,
)
from ...domain.skill_catalog import (
    catalog_summary_for_prompt,
    resolve_route_keys,
    skill_instructions_bundle,
)
from ...domain.turn_policy import is_genuine_user_gap, silence_process_reply
from ..state import AgentState


def ingest_node(state: AgentState) -> dict:
    """标准化输入：递增 run_version，取消旧 waiting 续跑。"""
    previous = int(state.get("run_version") or 0)
    new_version = previous + 1
    cancelled = list(state.get("cancelled_run_versions") or [])
    if state.get("terminal_status") == "waiting_external" or state.get("waiting_external_event"):
        if previous and previous not in cancelled:
            cancelled.append(previous)
    # events 使用 reducer：本节点只追加增量；整轮重置在 run_agent_turn input 完成
    return {
        "run_version": new_version,
        "cancelled_run_versions": cancelled,
        "terminal_status": "running",
        "waiting_external_event": False,
        "needs_user_input": False,
        "pending_runs": [],
        "current_step_id": None,
        "tool_result": None,
        "react_mode": False,
        "react_step": 0,
        "max_react_steps": 8,
        "react_decision": "act",
        "observations": [],
        "events": [{"type": "ingest", "run_version": new_version}],
        "executed_results": [{"__replace_results__": True}],
        "contract_violations": [{"__replace_violations__": True}],
    }


def _prior_user_goal(recent_messages: list[dict[str, Any]] | None, current: str) -> str:
    """取上一条非选项短回复的用户需求，供 A/B 续跑拼指令。"""
    from ...domain.llm_prompt import resolve_option_choice

    cur = (current or "").strip()
    for msg in reversed(list(recent_messages or [])):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").lower() != "user":
            continue
        text = str(msg.get("content") or "").strip()
        if not text or text == cur:
            continue
        resolved, matched = resolve_option_choice(text, recent_messages)
        if matched and resolved != text:
            continue
        if len(text) <= 2 and text.upper() in {"A", "B", "C", "D", "1", "2", "3", "4"}:
            continue
        return text[:200]
    return ""


def classify_intent_node(state: AgentState) -> dict:
    from ...domain.llm_prompt import resolve_option_choice

    raw = state.get("user_content") or ""
    recent = list(state.get("recent_messages") or [])
    resolved, matched = resolve_option_choice(raw, recent)
    effective = raw
    out: dict[str, Any] = {}
    if matched:
        prior = _prior_user_goal(recent, raw)
        prior_bit = f"延续需求「{prior}」。" if prior else ""
        effective = (
            f"{resolved}。{prior_bit}"
            "请立刻按该选项推进创作并在画布落节点（项目简报→分镜/画面），"
            "禁止只口头说明、不做 create_nodes。"
        )
        out["user_content"] = effective

    intent = classify_intent_hybrid(
        effective,
        api_key=settings.llm_api_key or None,
        base_url=settings.normalized_llm_base_url(),
        model=settings.llm_model,
        recent_messages=recent,
        project_memories=state.get("project_memories"),
        long_term_prefs=state.get("long_term_prefs"),
        canvas_context=state.get("canvas_context"),
        observations=state.get("observations"),
    )
    if matched:
        # 点选上轮方案 = 继续执行，禁止掉进「只讨论不写画布」
        intent.wants_execution = True
        if intent.name in ("discussion", "unknown"):
            intent.name = "workflow_orchestration"
        intent.reasons = list(intent.reasons or []) + [f"用户点选上轮选项：{matched}"]

    # 兼容旧字段
    legacy_map = {
        "discussion": "directions",
        "workflow_orchestration": "orchestrate_workflow",
        "advance_pipeline": "advance_pipeline",
        "regenerate_stale": "reregenerate_stale",
        "direct_canvas_action": "generate",
        "edit_existing": "update",
        "unknown": "general",
    }
    out.update({
        "intent": intent.model_dump(),
        "intent_type": legacy_map.get(intent.name, "general"),
        "events": [{
            "type": "intent",
            "name": intent.name,
            "confidence": intent.confidence,
            "wants_execution": intent.wants_execution,
            "requested_skill": intent.requested_skill,
            "reasons": intent.reasons,
        }],
    })
    return out


def _llm_next_actions_for_discussion(
    *,
    content: str,
    reply: str,
    canvas_context: dict[str, Any],
) -> list[str]:
    """讨论/兜底路径：由 LLM 基于上下文生成下一步建议；失败返回空。"""
    if not settings.llm_api_key:
        return []
    try:
        from ...agent.planner import llm_suggest_next_actions

        return llm_suggest_next_actions(
            content=content,
            reply=reply,
            pipeline_stage="discussion",
            actions=[],
            canvas_context=canvas_context,
            api_key=settings.llm_api_key,
            base_url=settings.normalized_llm_base_url(),
            model=settings.llm_model,
        )
    except Exception:
        return []


def answer_discussion_node(state: AgentState) -> dict:
    """讨论态：只回答，不写画布。"""
    from ...domain.intent_classifier import is_chitchat

    content = state.get("user_content") or ""
    ctx = state.get("canvas_context") or {}
    reply = ""
    if is_chitchat(content):
        reply = (
            "你好，我是 Paper Agent，可以帮你在画布上搭节点、连依赖、提交生成。"
            "直接说想做的内容就行，比如「创建一张小狗图片」或「搭一条竖屏短剧」。"
        )
    elif settings.llm_api_key:
        try:
            import httpx

            from ...domain.llm_prompt import build_chat_messages

            messages = build_chat_messages(
                user_content=content,
                persona=AGENT_PERSONA,
                skill_instructions=PAPER_AGENT_INSTRUCTIONS,
                extra_rules=(
                    "当前为讨论态：只给判断与方案，禁止规划 create/submit。"
                    "用语简洁，创作者语言。"
                    "末尾不要罗列固定建议词表；下一步建议由 next_actions 字段另行产出。"
                ),
                include_tools=True,
                include_skills_catalog=True,
                recent_messages=state.get("recent_messages"),
                project_memories=state.get("project_memories"),
                long_term_prefs=state.get("long_term_prefs"),
                observations=state.get("observations"),
                executed_results=state.get("executed_results"),
                canvas_context=ctx,
                selected_nodes=list(state.get("selected_nodes") or []),
            )
            base = settings.normalized_llm_base_url()
            resp = httpx.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": 0.4,
                },
                timeout=60,
            )
            resp.raise_for_status()
            reply = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:
            reply = f"当前无法调用模型回答（{str(exc)[:80]}）。请稍后重试，或改成明确执行指令。"
    else:
        reply = (
            "这是讨论/咨询。我可以说明排版、镜头或工作流怎么拆；"
            "若要我动手搭建，请直接说清楚你想生成什么、做到哪一步。"
        )
    if not (reply or "").strip():
        reply = "在呢。说说你想创作什么，或点选下一步建议。"
    next_actions = _llm_next_actions_for_discussion(
        content=content,
        reply=reply,
        canvas_context=ctx,
    )
    if is_chitchat(content) and not next_actions:
        next_actions = ["创建一张图片", "搭建竖屏短剧"]
    return {
        "reply": reply,
        "reply_type": "directions",
        "planned_actions": [],
        "executable_actions": [],
        "pending_high_risk": [],
        "terminal_status": "completed",
        "next_actions": next_actions,
    }


def fallback_node(state: AgentState) -> dict:
    content = state.get("user_content") or ""
    ctx = state.get("canvas_context") or {}
    reply = (
        "我还没完全理解你的意图。你可以继续说明想做的镜头/画布操作，"
        "或直接下达可执行指令（例如搭建某条链路、推进下一阶段、修改选中节点）。"
    )
    next_actions = _llm_next_actions_for_discussion(
        content=content,
        reply=reply,
        canvas_context=ctx,
    )
    return {
        "reply": reply,
        "reply_type": "general",
        "planned_actions": [],
        "terminal_status": "completed",
        "next_actions": next_actions,
    }


def acquire_context_node(state: AgentState) -> dict:
    """按需读画布：直接动作 / 编辑前补事实。复用已有 canvas_context，缺则标 query。"""
    ctx = state.get("canvas_context") or {}
    out: dict[str, Any] = {"query_scope": "related"}
    if not ctx.get("nodeCount") and state.get("canvas_id"):
        out["events"] = [{"type": "context_needed", "reason": "缺画布摘要"}]
    return out


def select_skill_node(state: AgentState) -> dict:
    """按意图 requested_skill 选择工作流 Skill；不默认竖屏短剧。"""
    intent = intent_from_dict(state.get("intent"))
    keys = resolve_route_keys(intent.requested_skill)
    return {
        "selected_skill_keys": keys,
        "skill_name": "+".join(keys) if keys else (state.get("skill_name") or "paper-agent-default"),
        "events": [{"type": "skill_selected", "keys": keys, "catalog_hint": True}],
    }


def load_skill_node(state: AgentState) -> dict:
    keys = list(state.get("selected_skill_keys") or [])
    bundle = skill_instructions_bundle(keys) if keys else ""
    base = PAPER_AGENT_INSTRUCTIONS
    summary = catalog_summary_for_prompt(16)
    instructions = f"{base}\n\n{summary}"
    if bundle:
        instructions = f"{instructions}\n\n{bundle}"
    return {
        "skill_instructions": instructions,
        "events": [{"type": "skill_loaded", "skill": state.get("skill_name"), "keys": keys}],
    }


def create_plan_node(state: AgentState) -> dict:
    """创意规划（LLM 内容）+ 执行编译（工具步骤）→ StructuredPlan。"""
    intent = state.get("intent") or {}
    if not isinstance(intent, dict):
        intent = intent_from_dict(intent).model_dump()
    plan = build_structured_plan(
        state.get("user_content") or "",
        intent=intent,
        skill_keys=list(state.get("selected_skill_keys") or []),
        canvas_context=state.get("canvas_context"),
        api_key=settings.llm_api_key or None,
        base_url=settings.normalized_llm_base_url(),
        model=settings.llm_model,
        recent_messages=state.get("recent_messages"),
        project_memories=state.get("project_memories"),
        long_term_prefs=state.get("long_term_prefs"),
        observations=state.get("observations"),
        selected_nodes=list(state.get("selected_nodes") or []),
    )
    new_events: list[dict[str, Any]] = []
    if plan.thinking:
        new_events.append({"type": "thinking", "content": plan.thinking})
    for step in plan.steps:
        new_events.append({
            "type": "plan_step",
            "tool": (step.payload or {}).get("tool"),
            "summary": step.title,
            "reasoning": step.purpose,
            "step_id": step.id,
            "kind": step.kind,
        })
    return {
        "plan": plan_to_dict(plan),
        "reply": silence_process_reply(plan.reply or state.get("reply") or ""),
        "next_actions": plan.next_actions or [],
        "events": new_events,
    }


def reconcile_canvas_node(state: AgentState) -> dict:
    """推进未完成流程：标记为 advance，交给 create_plan（铁路）编译。"""
    intent = dict(state.get("intent") or {})
    intent["name"] = "advance_pipeline"
    intent["wants_execution"] = True
    return {
        "intent": intent,
        "selected_skill_keys": list(state.get("selected_skill_keys") or []),
        "react_mode": False,
        "events": [{"type": "reconcile", "scope": "pipeline"}],
        "waiting_external_event": False,
        "terminal_status": "running",
    }


def plan_recovery_node(state: AgentState) -> dict:
    intent = dict(state.get("intent") or {})
    intent["name"] = "regenerate_stale"
    intent["wants_execution"] = True
    return {
        "intent": intent,
        "selected_skill_keys": [],
        "react_mode": False,
        "skill_instructions": state.get("skill_instructions") or PAPER_AGENT_INSTRUCTIONS,
    }


def validate_plan_node(state: AgentState) -> dict:
    """约束校验 + 编译为旧 planned_actions，桥接 risk_classifier/executor。"""
    plan = plan_from_dict(state.get("plan"))

    if not plan or not plan.steps:
        return {
            "validation_route": "finalize",
            "planned_actions": [],
            "executable_actions": [],
            "pending_high_risk": [],
            "reply": state.get("reply") or "当前没有可执行步骤。",
            "terminal_status": "completed",
        }

    if plan.user_decision_required:
        intent = intent_from_dict(state.get("intent"))
        q = (plan.constraints or {}).get("ask_question") or plan.reply or ""
        genuine = is_genuine_user_gap(
            question=q,
            content=state.get("user_content") or "",
            wants_execution=bool(intent.wants_execution),
            has_steps=bool(plan.steps),
            selected_nodes=list(state.get("selected_nodes") or []),
            canvas=state.get("canvas_context") or {},
        )
        if genuine and not plan.steps:
            q = q or "还缺具体主题/人物/风格，补一句我就能继续搭。"
            return {
                "validation_route": "ask_user",
                "needs_user_input": True,
                "terminal_status": "waiting_user",
                "reply": q,
                "events": [{"type": "ask_user", "question": q}],
            }
        # 已有可执行步骤：不打断，把提问降为 thinking
        plan.user_decision_required = False

    # 讨论意图不应带写操作
    intent = intent_from_dict(state.get("intent"))
    if not intent.wants_execution and intent.name == "discussion":
        plan.steps = [s for s in plan.steps if s.kind in ("read", "query", "respond")]

    actions = steps_to_planned_actions(plan)
    return {
        "plan": plan_to_dict(plan),
        "planned_actions": actions,
        "validation_route": "execute" if actions else "finalize",
        "reply": silence_process_reply(plan.reply or state.get("reply") or ""),
        "next_actions": plan.next_actions or state.get("next_actions") or [],
        "events": [{
            "type": "plan_validated",
            "step_count": len(plan.steps),
            "action_count": len(actions),
        }],
        "terminal_status": "running",
    }


def request_user_input_node(state: AgentState) -> dict:
    """等待用户决策：本轮先落回复；完整 interrupt 可后续接线。"""
    plan = plan_from_dict(state.get("plan"))
    q = ""
    if plan:
        q = str((plan.constraints or {}).get("ask_question") or "")
    reply = q or state.get("reply") or "请补充关键决策后继续。"
    return {
        "reply": reply,
        "needs_user_input": True,
        "terminal_status": "waiting_user",
        "planned_actions": [],
        "executable_actions": [],
        "pending_high_risk": [],
    }


def finalize_node(state: AgentState) -> dict:
    plan = plan_from_dict(state.get("plan"))
    pending = state.get("pending_runs") or []
    complete = is_task_complete(plan, pending) if plan else True
    reply = state.get("reply") or ""
    status = state.get("terminal_status") or "completed"

    if state.get("waiting_external_event"):
        status = "waiting_external"
        if reply and "正在" not in reply and "queued" not in reply.lower():
            reply = (reply + "\n素材仍在生成中，上游就绪后会继续。").strip()
    elif plan and any(s.status == "failed" for s in plan.steps):
        status = "failed"
    elif complete:
        status = "completed"

    return {
        "terminal_status": status,
        "reply": reply,
        "events": [{"type": "finalize", "terminal_status": status}],
    }


def route_after_intent(state: AgentState) -> str:
    intent = intent_from_dict(state.get("intent"))
    return route_intent_name(intent)


def route_after_select_skill(state: AgentState) -> str:
    # 无论是否命中具体 Skill，都注入目录摘要，供创意规划按语义选择
    return "load_skill"


def route_after_validate(state: AgentState) -> str:
    route = state.get("validation_route") or "finalize"
    if route == "ask_user":
        return "ask_user"
    if route == "execute":
        return "execute"
    return "finalize"
