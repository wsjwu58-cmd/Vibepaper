"""编译 LangGraph StateGraph，提供 turn / resume 入口。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..core.config import settings
from .nodes import (
    acquire_context_node,
    answer_discussion_node,
    check_task_status_node,
    classify_intent_node,
    clock_node,
    confirmer_node,
    context_builder_node,
    create_plan_node,
    executor_node,
    fallback_node,
    finalize_node,
    ingest_node,
    load_skill_node,
    memory_updater_node,
    parallel_merge_node,
    plan_recovery_node,
    reconcile_canvas_node,
    reflect_node,
    reply_builder_node,
    request_user_input_node,
    risk_classifier_node,
    select_skill_node,
    tool_worker_node,
    validate_plan_node,
)
from .nodes.orchestration_nodes import (
    route_after_intent,
    route_after_select_skill,
    route_after_validate,
)
from .routing import (
    route_after_check_status,
    route_after_exec,
    route_after_reflect,
    route_by_confirm,
    route_by_risk,
)
from .state import AgentState

logger = logging.getLogger("agent.graph")

_graph = None
_wakeup_graph = None
_checkpointer = None
_lock = threading.Lock()


def _psycopg_conninfo() -> str:
    url = settings.database_url
    # postgresql+psycopg2://user:pass@host:port/db → postgresql://...
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url[len("postgresql+psycopg2://"):]
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    return url


def _build_checkpointer():
    """PostgresSaver 优先；失败则 MemorySaver（保证服务可启动）。"""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        conninfo = _psycopg_conninfo()
        pool = ConnectionPool(
            conninfo=conninfo,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            min_size=1,
            max_size=5,
            open=True,
        )
        saver = PostgresSaver(pool)
        saver.setup()
        logger.info("LangGraph checkpointer: PostgresSaver")
        return saver
    except Exception as e:
        logger.warning("PostgresSaver unavailable (%s), falling back to MemorySaver", e)
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


def build_graph(checkpointer=None):
    """意图分流 → 创意规划/执行编译 → 确认/执行 → 依赖链推进（clock）→ 收尾。"""
    g = StateGraph(AgentState)

    g.add_node("ingest", ingest_node)
    g.add_node("context_builder", context_builder_node)
    g.add_node("classify_intent", classify_intent_node)

    g.add_node("answer_discussion", answer_discussion_node)
    g.add_node("fallback", fallback_node)
    g.add_node("acquire_context", acquire_context_node)
    g.add_node("reconcile_canvas", reconcile_canvas_node)
    g.add_node("plan_recovery", plan_recovery_node)
    g.add_node("select_skill", select_skill_node)
    g.add_node("load_skill", load_skill_node)
    g.add_node("create_plan", create_plan_node)
    g.add_node("validate_plan", validate_plan_node)
    g.add_node("request_user_input", request_user_input_node)

    g.add_node("risk_classifier", risk_classifier_node)
    g.add_node("executor", executor_node)
    g.add_node("tool_worker", tool_worker_node)
    g.add_node("parallel_merge", parallel_merge_node)
    g.add_node("reflect", reflect_node)
    g.add_node("confirmer", confirmer_node)
    g.add_node("clock_node", clock_node)

    g.add_node("finalize", finalize_node)
    g.add_node("reply_builder", reply_builder_node)
    g.add_node("memory_updater", memory_updater_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "context_builder")
    g.add_edge("context_builder", "classify_intent")

    g.add_conditional_edges("classify_intent", route_after_intent, {
        "answer_discussion": "answer_discussion",
        "acquire_context": "acquire_context",
        "reconcile_canvas": "reconcile_canvas",
        "plan_recovery": "plan_recovery",
        "select_skill": "select_skill",
        "fallback": "fallback",
    })

    g.add_edge("answer_discussion", "finalize")
    g.add_edge("fallback", "finalize")
    g.add_edge("acquire_context", "select_skill")
    g.add_edge("reconcile_canvas", "create_plan")
    g.add_edge("plan_recovery", "create_plan")

    g.add_conditional_edges("select_skill", route_after_select_skill, {
        "load_skill": "load_skill",
        "create_plan": "create_plan",
    })
    g.add_edge("load_skill", "create_plan")
    g.add_edge("create_plan", "validate_plan")

    g.add_conditional_edges("validate_plan", route_after_validate, {
        "ask_user": "request_user_input",
        "execute": "risk_classifier",
        "finalize": "finalize",
    })
    g.add_edge("request_user_input", "finalize")

    g.add_conditional_edges("risk_classifier", route_by_risk, {
        "execute": "executor",
        "confirm": "confirmer",
        "done": "finalize",
    })
    g.add_conditional_edges("confirmer", route_by_confirm, {
        "accept": "executor",
        "reject": "finalize",
    })
    g.add_conditional_edges("executor", route_after_exec, {
        "confirm": "confirmer",
        "wait_for_result": "clock_node",
        "reflect": "reflect",
        "continue": "create_plan",
        "done": "finalize",
    })
    g.add_edge("tool_worker", "parallel_merge")
    g.add_conditional_edges("parallel_merge", route_after_exec, {
        "confirm": "confirmer",
        "wait_for_result": "clock_node",
        "reflect": "reflect",
        "continue": "create_plan",
        "done": "finalize",
    })
    g.add_conditional_edges("reflect", route_after_reflect, {
        "replan": "create_plan",
        "reply": "finalize",
    })
    g.add_edge("clock_node", "finalize")
    g.add_edge("finalize", "reply_builder")
    g.add_edge("reply_builder", "memory_updater")
    g.add_edge("memory_updater", END)
    return g.compile(checkpointer=checkpointer)


def build_wakeup_graph(checkpointer=None):
    """clock 唤醒专用子图：check_task_status → (reclock) → reply。"""
    g = StateGraph(AgentState)
    g.add_node("check_task_status", check_task_status_node)
    g.add_node("clock_node", clock_node)
    g.add_node("reply_builder", reply_builder_node)
    g.add_edge(START, "check_task_status")
    g.add_conditional_edges("check_task_status", route_after_check_status, {
        "reclock": "clock_node",
        "reply": "reply_builder",
    })
    g.add_edge("clock_node", "reply_builder")
    g.add_edge("reply_builder", END)
    return g.compile(checkpointer=checkpointer)


def get_wakeup_graph():
    """唤醒子图不使用 checkpointer，避免与主会话 thread_id 争用导致死锁。"""
    global _wakeup_graph
    with _lock:
        if _wakeup_graph is None:
            _wakeup_graph = build_wakeup_graph(checkpointer=None)
        return _wakeup_graph


def run_agent_wakeup(
    session_id: int,
    user_id: int,
    canvas_id: int | None,
    note: dict,
) -> list[dict]:
    """clock 唤醒：经 LangGraph 入口执行 check_task_status 并 SSE 推送。"""
    from ..core.db import SessionLocal
    from ..services.session_events import publish_session_event
    from ..services.session_service import session_service

    graph = get_wakeup_graph()
    initial: AgentState = {
        "session_id": session_id,
        "user_id": user_id,
        "canvas_id": canvas_id,
        "canvas_version": 1,
        "user_content": "",
        "selected_nodes": [],
        "intent_type": "wakeup",
        "query_scope": "none",
        "canvas_context": {},
        "skill_instructions": "",
        "skill_name": "",
        "recent_messages": [],
        "project_memories": [],
        "long_term_prefs": [],
        "planned_actions": [],
        "pending_high_risk": [],
        "executable_actions": [],
        "executed_results": [],
        "confirm_accept": None,
        "pending_confirm": None,
        "reply_type": "task_status",
        "pipeline_stage": "text_base",
        "suggestions": [],
        "next_actions": [],
        "reply": "",
        "events": [],
        "context_token_estimate": 0,
        "telemetry": [],
        "reflection_count": 0,
        "needs_reflection": False,
        "reflection_note": "",
        "contract_violations": [],
        "current_action": {},
        "wakeup_note": note,
        "needs_reclock": False,
    }
    # 独立 thread_id，绝不复用主对话 checkpoint
    task_key = str(note.get("task_id") or "na")
    config = {
        "configurable": {"thread_id": f"wakeup-{session_id}-{task_key}"},
        "recursion_limit": 20,
    }
    try:
        result = graph.invoke(initial, config=config)
    except Exception as e:
        logger.exception("wakeup graph failed")
        events = [{"type": "task_status", "data": {"error": str(e)[:200]}}]
        publish_session_event(session_id, events[0])
        return events

    events: list[dict] = []
    if isinstance(result, dict):
        events = list(result.get("events") or [])
        # reply_builder 已写入 assistant_message 时不再重复
        if result.get("reply") and not any(e.get("type") == "assistant_message" for e in events):
            events.append({
                "type": "assistant_message",
                "content": result["reply"],
                "replyType": result.get("reply_type", "task_status"),
                "nextActions": result.get("next_actions") or [],
                "executionSteps": [],
            })
    # 持久化非静默回复，避免 UI 只靠 SSE 丢消息
    db = SessionLocal()
    try:
        for ev in events:
            publish_session_event(session_id, ev)
            if ev.get("type") == "assistant_message" and ev.get("content") and not ev.get("silent"):
                session_service.add_message(
                    db, session_id, "assistant", ev["content"],
                    msg_type="text",
                    meta={
                        "replyType": ev.get("replyType") or "task_status",
                        "nextActions": ev.get("nextActions") or [],
                        "source": "wakeup",
                    },
                )
    finally:
        db.close()
    return events


def prune_stale_checkpoints(max_age_seconds: int | None = None) -> int:
    """清理过期 LangGraph checkpoint（PostgresSaver）。"""
    ttl = max_age_seconds or settings.checkpoint_ttl_seconds
    try:
        from psycopg_pool import ConnectionPool
        conninfo = _psycopg_conninfo()
        pool = ConnectionPool(conninfo=conninfo, min_size=1, max_size=2, open=True)
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM checkpoints WHERE created_at < NOW() - (%s || ' seconds')::interval",
                    (str(ttl),),
                )
                deleted = cur.rowcount or 0
        pool.close()
        return deleted
    except Exception as e:
        logger.debug("prune_stale_checkpoints skipped: %s", e)
        return 0


def get_agent_graph():
    global _graph, _checkpointer
    with _lock:
        if _graph is None:
            _checkpointer = _build_checkpointer()
            _graph = build_graph(_checkpointer)
        return _graph


def _config(session_id: int) -> dict:
    return {
        "configurable": {"thread_id": str(session_id)},
        "recursion_limit": 40,
    }


def _collect_interrupt_events(result: Any) -> list[dict]:
    """从 interrupt 结果提取 confirm_required 事件。"""
    events = []
    interrupts = None
    if isinstance(result, dict) and "__interrupt__" in result:
        interrupts = result["__interrupt__"]
    if interrupts:
        for item in interrupts:
            val = getattr(item, "value", item)
            if isinstance(val, dict):
                events.append(val if val.get("type") else {**val, "type": "confirm_required"})
    return events


def find_pending_confirm_action_id(session_id: int) -> int | None:
    """查找 LangGraph 中断或 DB 中待确认的高风险 action。"""
    from ..core.db import SessionLocal
    from ..models import AgentAction

    graph = get_agent_graph()
    config = _config(session_id)
    try:
        snap = graph.get_state(config)
        if snap and snap.next and "confirmer" in (snap.next or ()):
            for task in (snap.tasks or ()):
                for it in (getattr(task, "interrupts", ()) or ()):
                    val = getattr(it, "value", None)
                    if isinstance(val, dict) and val.get("actionId"):
                        return int(val["actionId"])
    except Exception:
        pass

    db = SessionLocal()
    try:
        row = (
            db.query(AgentAction)
            .filter(AgentAction.session_id == session_id, AgentAction.status == "pending")
            .order_by(AgentAction.id.desc())
            .first()
        )
        return int(row.id) if row else None
    finally:
        db.close()


def _events_from_graph_result(result: Any, initial: list[dict] | None = None) -> list[dict]:
    events: list[dict] = list(initial or [])
    seen: set[tuple] = set()
    for e in events:
        seen.add((e.get("type"), e.get("actionId"), e.get("tool"), e.get("content")))

    if isinstance(result, dict):
        for e in result.get("events") or []:
            key = (e.get("type"), e.get("actionId"), e.get("tool"), e.get("content"))
            if key not in seen:
                events.append(e)
                seen.add(key)
        reply = (result.get("reply") or "").strip()
        if reply and not any(x.get("type") == "assistant_message" for x in events):
            events.append({"type": "assistant_message", "content": reply})
    return events


def try_resume_dialog_confirm(session_id: int, user_id: int, accept: bool) -> list[dict] | None:
    """废弃的对话确认入口：高风险操作只能由确认卡 API 恢复。"""
    return None

    # 下面保留旧实现仅供历史 checkpoint 排障阅读；return 后不会执行。
    graph = get_agent_graph()
    config = _config(session_id)

    # 必须有挂起的 confirmer，否则交给正常 turn（避免「确认」被当新指令）
    has_interrupt = False
    event_watermark = 0
    try:
        snap = graph.get_state(config)
        if snap and snap.next and "confirmer" in (snap.next or ()):
            has_interrupt = True
        if snap and isinstance(getattr(snap, "values", None), dict):
            event_watermark = len(snap.values.get("events") or [])
    except Exception:
        pass

    action_id = find_pending_confirm_action_id(session_id)
    if not action_id and not has_interrupt:
        return None

    result = resume_agent_confirm(
        session_id, user_id, int(action_id or 0), accept,
    )

    if not result or not result.get("ok"):
        return [
            {"type": "assistant_message", "content": (result or {}).get("error") or "确认失败"},
            {"type": "done"},
        ]
    if result.get("cancelled"):
        return [
            {"type": "assistant_message", "content": "已取消操作。"},
            {"type": "done"},
        ]
    inner = (result.get("result") or {})
    graph_result = inner if isinstance(inner, dict) and inner.get("events") is not None else result
    all_events = list((graph_result or {}).get("events") or []) if isinstance(graph_result, dict) else []
    # 只回传 interrupt 之后的增量，避免前端把规划过程重放一遍
    delta = all_events[event_watermark:] if event_watermark and len(all_events) >= event_watermark else all_events
    keep_types = {
        "inline_confirm", "action_result", "assistant_message", "confirm_required",
        "usage", "done", "task_status", "clock_scheduled", "contract_blocked",
    }
    events: list[dict] = []
    for e in delta:
        if not isinstance(e, dict):
            continue
        if e.get("__replace_events__") or e.get("__replace_results__"):
            continue
        if e.get("type") in keep_types:
            # 收尾消息去掉历史 executionSteps，只留本拍结果
            if e.get("type") == "assistant_message" and e.get("executionSteps"):
                steps = [
                    s for s in (e.get("executionSteps") or [])
                    if isinstance(s, dict) and s.get("kind") in ("result", "speech")
                ]
                e = {**e, "executionSteps": steps}
            events.append(e)

    if not any(e.get("type") == "assistant_message" for e in events):
        reply = ""
        if isinstance(graph_result, dict):
            reply = str(graph_result.get("reply") or "").strip()
        msg = reply or ("已确认并继续执行。" if accept else "已取消操作。")
        events.append({"type": "assistant_message", "content": msg})
    if not any(e.get("type") == "done" for e in events):
        events.append({"type": "done"})
    return events


def run_agent_turn(
    session_id: int,
    user_id: int,
    canvas_id: int | None,
    content: str,
    selected_nodes: list[int] | None,
) -> list[dict]:
    """执行一轮对话，返回 SSE 事件列表。"""
    from .confirm_helpers import parse_confirm_intent
    from .state import reset_events, reset_executed_results

    # 高风险操作不能由聊天文字确认或取消；只能消费确认卡的一次性令牌。
    confirm_intent = parse_confirm_intent(content)
    if confirm_intent:
        return [
            {
                "type": "assistant_message",
                "content": "高风险操作必须在确认卡片中确认或取消；普通聊天文本不会触发执行。",
            },
            {"type": "done"},
        ]

    graph = get_agent_graph()
    config = _config(session_id)

    # 有待确认动作时，拒绝继续在同一 checkpoint 规划，避免新指令隐式取消或
    # 绕过签名令牌恢复。
    try:
        snap = graph.get_state(config)
        if snap and snap.next and "confirmer" in (snap.next or ()):
            return [
                {
                    "type": "assistant_message",
                    "content": "当前有待确认的高风险操作，请先在确认卡片中确认或取消后再继续。",
                    "requiresConfirmationCard": True,
                },
                {"type": "done"},
            ]
    except Exception:
        logger.warning("read pending confirmer interrupt failed session=%s", session_id, exc_info=True)

    initial: AgentState = {
        "session_id": session_id,
        "user_id": user_id,
        "canvas_id": canvas_id,
        "canvas_version": 1,
        "user_content": content,
        "selected_nodes": [int(x) for x in (selected_nodes or [])],
        "intent_type": "general",
        "query_scope": "summary",
        "canvas_context": {},
        "skill_instructions": "",
        "skill_name": "",
        "recent_messages": [],
        "project_memories": [],
        "long_term_prefs": [],
        "react_mode": False,
        "react_step": 0,
        "max_react_steps": 8,
        "react_decision": "act",
        "observations": [],
        "run_version": 0,
        "cancelled_run_versions": [],
        "intent": {},
        "selected_skill_keys": [],
        "plan": {},
        "pending_runs": [],
        "current_step_id": None,
        "tool_result": None,
        "needs_user_input": False,
        "waiting_external_event": False,
        "terminal_status": "running",
        "validation_route": "",
        "confirmed_action": None,
        "generation_preferences": {},
        "planned_actions": [],
        "pending_high_risk": [],
        "executable_actions": [],
        # 关键：丢掉 checkpoint 里可能膨胀到数百 MB 的历史列表
        "executed_results": reset_executed_results(),
        "confirm_accept": None,
        "pending_confirm": None,
        "reply_type": "general",
        "pipeline_stage": "text_base",
        "suggestions": [],
        "next_actions": [],
        "reply": "",
        "events": reset_events({"type": "user_message", "content": content}),
        "context_token_estimate": 0,
        "telemetry": [],
        "reflection_count": 0,
        "needs_reflection": False,
        "reflection_note": "",
        "contract_violations": [{"__replace_violations__": True}],
        "current_action": {},
        "wakeup_note": {},
        "needs_reclock": False,
    }

    events: list[dict] = [{"type": "user_message", "content": content}]

    try:
        result = graph.invoke(initial, config=config)
    except Exception as e:
        # 某些版本 interrupt 以异常形式抛出
        from langgraph.errors import GraphInterrupt
        if isinstance(e, GraphInterrupt) or e.__class__.__name__ == "GraphInterrupt":
            inter = getattr(e, "interrupts", None) or getattr(e, "args", [{}])[0]
            payload = inter[0].value if inter and hasattr(inter[0], "value") else (
                inter[0] if isinstance(inter, (list, tuple)) and inter else {}
            )
            if isinstance(payload, dict):
                events.append(payload if payload.get("type") else {**payload, "type": "confirm_required"})
            from .confirm_helpers import build_dialog_confirm_prompt
            prompt = "请在确认卡片中确认或取消；普通聊天文本不能替代确认。"
            if isinstance(payload, dict) and payload.get("summary"):
                prompt = build_dialog_confirm_prompt({
                    "tool_name": payload.get("tool"),
                    "summary": payload.get("summary"),
                    "params": {"estimated_cost": payload.get("estimatedCost") or 0},
                }, chain_cost=int(payload.get("chainEstimatedCost") or 0))
            events.append({
                "type": "assistant_message",
                "content": prompt,
                "requiresConfirmationCard": True,
            })
            events.append({"type": "done"})
            return events
        logger.exception("graph invoke failed")
        events.append({"type": "assistant_message", "content": f"Agent 执行失败：{str(e)[:200]}"})
        events.append({"type": "done"})
        return events

    # interrupt 未抛异常时：合并 state.events + __interrupt__
    if isinstance(result, dict):
        state_events = result.get("events") or []
        seen_types_ids = set()
        for e in state_events:
            if not isinstance(e, dict) or e.get("__replace_events__") or e.get("__replace_results__"):
                continue
            key = (e.get("type"), e.get("actionId"), e.get("tool"), e.get("content"))
            if key not in seen_types_ids:
                events.append(e)
                seen_types_ids.add(key)
        for e in _collect_interrupt_events(result):
            key = (e.get("type"), e.get("actionId"), e.get("tool"), e.get("content"))
            if key not in seen_types_ids:
                events.append(e)
                seen_types_ids.add(key)
        snap = graph.get_state(config)
        if snap and snap.next and "confirmer" in (snap.next or ()):
            for task in (snap.tasks or []):
                interrupts = getattr(task, "interrupts", ()) or ()
                for it in interrupts:
                    val = getattr(it, "value", None)
                    if isinstance(val, dict) and not any(
                        x.get("actionId") == val.get("actionId") for x in events
                    ):
                        events.append(val if val.get("type") else {**val, "type": "confirm_required"})
            if not any(e.get("type") == "assistant_message" for e in events):
                from .confirm_helpers import build_dialog_confirm_prompt
                confirm_ev = next((e for e in events if e.get("type") == "confirm_required"), None)
                if confirm_ev:
                    prompt = build_dialog_confirm_prompt({
                        "tool_name": confirm_ev.get("tool"),
                        "summary": confirm_ev.get("summary"),
                        "params": {"estimated_cost": confirm_ev.get("estimatedCost") or 0},
                    }, chain_cost=int(confirm_ev.get("chainEstimatedCost") or 0))
                else:
                    prompt = "请在确认卡片中确认或取消；普通聊天文本不能替代确认。"
                events.append({
                    "type": "assistant_message",
                    "content": prompt,
                    "requiresConfirmationCard": True,
                })

    # usage
    token_est = 0
    if isinstance(result, dict):
        token_est = int(result.get("context_token_estimate") or 0)
        reply = result.get("reply") or ""
        token_est += max(1, int(len(content + reply) / 1.5))
    events.append({"type": "usage", "tokenUsed": token_est, "totalTokens": token_est,
                   "contextTokenEstimate": (result or {}).get("context_token_estimate") if isinstance(result, dict) else 0})
    if not any(e.get("type") == "done" for e in events):
        events.append({"type": "done"})
    return events


def resume_agent_confirm(
    session_id: int,
    user_id: int,
    action_id: int,
    accept: bool,
    approval_token: str | None = None,
    expected_canvas_version: int | None = None,
    confirmed_action: dict | None = None,
) -> dict:
    """从 checkpoint resume 确认。"""
    from ..core.db import SessionLocal
    from ..models import AgentAction, AgentSession
    from ..domain.approval import compute_action_hash
    from ..services.approval_service import (
        ApprovalError,
        consume_approval,
        mark_action_approved,
    )
    from ..services.telemetry import agent_confirm_accept, agent_confirm_reject
    from ..tools.registry import headers_for
    import httpx

    graph = get_agent_graph()
    config = _config(session_id)

    # 不允许缺少 Action/令牌的 checkpoint 兜底恢复，否则会绕过审批。
    if int(action_id or 0) <= 0:
        return {"ok": False, "error": "确认记录不存在", "error_code": "CONFIRMATION_REQUIRED"}

    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if not session or session.user_id != user_id:
            return {"ok": False, "error": "会话不存在"}
        record = db.get(AgentAction, action_id)
        if not record or record.session_id != session_id:
            return {"ok": False, "error": "确认记录不存在", "error_code": "CONFIRMATION_REQUIRED"}

        if not (approval_token or "").strip():
            return {"ok": False, "error": "缺少确认令牌", "error_code": "CONFIRMATION_REQUIRED"}

        # 卡片编辑参数会改变动作摘要；必须重新规划并签发新的确认，不能复用旧 token。
        if confirmed_action and isinstance(confirmed_action, dict):
            return {
                "ok": False,
                "error": "确认参数已变化，请重新发送指令以获取新的确认卡片",
                "error_code": "VERSION_CONFLICT",
            }

        # checkpoint TTL：中断超过 5 分钟则确认失效
        event_watermark = 0
        try:
            from datetime import datetime, timezone
            snap = graph.get_state(config)
            if snap and getattr(snap, "created_at", None):
                created = snap.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - created).total_seconds()
                if age > settings.checkpoint_ttl_seconds:
                    return {
                        "ok": False,
                        "error": "确认已超时，请重新发送指令",
                        "error_code": "CONFIRM_EXPIRED",
                    }
            if snap and isinstance(getattr(snap, "values", None), dict):
                event_watermark = len(snap.values.get("events") or [])
        except Exception:
            pass

        current_canvas_version = int(record.canvas_version or 0)
        # 画布版本是令牌绑定的一部分。无法读取最新版本时默认拒绝，而非放行旧审批。
        if session.canvas_id:
            try:
                r = httpx.get(
                    f"{settings.canvas_base_url}/internal/canvases/{session.canvas_id}/summary",
                    headers=headers_for(user_id),
                    timeout=8,
                    trust_env=False,
                )
            except Exception:
                return {"ok": False, "error": "无法校验画布版本，请稍后重试", "error_code": "CANVAS_UNAVAILABLE"}
            if r.status_code != 200:
                return {"ok": False, "error": "无法校验画布版本，请稍后重试", "error_code": "CANVAS_UNAVAILABLE"}
            current_canvas_version = int(r.json().get("version") or 0)

        action_hash = compute_action_hash(
            record.tool_name or "",
            record.params or {},
            int(record.approved_cost_cap or 0),
        )
        try:
            approval = consume_approval(
                db,
                token=approval_token,
                user_id=user_id,
                session_id=session_id,
                action_id=action_id,
                canvas_id=session.canvas_id,
                canvas_version=current_canvas_version or None,
                plan_version=int(record.plan_version or 1),
                action_hash=action_hash,
                accept=accept,
            )
        except ApprovalError as exc:
            db.rollback()
            return {"ok": False, "error": exc.message, "error_code": exc.code}

        if not accept:
            record.status = "rejected"
            db.commit()
            agent_confirm_reject(session_id, record.tool_name or "")
            # 仍 resume 以结束图
            try:
                graph.invoke(Command(resume={"accept": False, "actionId": action_id}), config=config)
            except Exception:
                pass
            return {
                "ok": True,
                "cancelled": True,
                "events": [{"type": "assistant_message", "content": "已取消操作。"}],
            }

        mark_action_approved(db, record, approval)
        db.commit()
        agent_confirm_accept(session_id, record.tool_name or "")
        result = graph.invoke(Command(resume={"accept": True, "actionId": action_id}), config=config)
        # executor 会把同步动作标为 executed、异步生成标为 waiting_terminal；此处
        # 不得覆盖它的真实执行状态。
        graph_result = result if isinstance(result, dict) else {}
        all_events = list(graph_result.get("events") or [])
        delta = all_events[event_watermark:] if event_watermark and len(all_events) >= event_watermark else all_events
        keep_types = {
            "inline_confirm", "action_result", "assistant_message", "confirm_required",
            "usage", "task_status", "clock_scheduled", "contract_blocked",
        }
        events = [
            event for event in delta
            if isinstance(event, dict)
            and not event.get("__replace_events__")
            and not event.get("__replace_results__")
            and event.get("type") in keep_types
        ]
        if not any(event.get("type") == "assistant_message" for event in events):
            events.append({"type": "assistant_message", "content": "已确认并继续执行。"})
        return {"ok": True, "events": events}
    finally:
        db.close()
