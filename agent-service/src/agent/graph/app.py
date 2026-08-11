"""编译 LangGraph StateGraph，提供 turn / resume 入口。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..core.config import settings
from .nodes import (
    check_task_status_node,
    clock_node,
    confirmer_node,
    context_builder_node,
    executor_node,
    memory_updater_node,
    parallel_merge_node,
    planner_node,
    reflect_node,
    reply_builder_node,
    risk_classifier_node,
    skill_loader_node,
    tool_worker_node,
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
    g = StateGraph(AgentState)
    g.add_node("context_builder", context_builder_node)
    g.add_node("skill_loader", skill_loader_node)
    g.add_node("planner", planner_node)
    g.add_node("risk_classifier", risk_classifier_node)
    g.add_node("executor", executor_node)
    g.add_node("tool_worker", tool_worker_node)
    g.add_node("parallel_merge", parallel_merge_node)
    g.add_node("reflect", reflect_node)
    g.add_node("confirmer", confirmer_node)
    g.add_node("clock_node", clock_node)
    g.add_node("reply_builder", reply_builder_node)
    g.add_node("memory_updater", memory_updater_node)

    g.add_edge(START, "context_builder")
    g.add_edge("context_builder", "skill_loader")
    g.add_edge("skill_loader", "planner")
    g.add_edge("planner", "risk_classifier")
    g.add_conditional_edges("risk_classifier", route_by_risk, {
        "execute": "executor",
        "confirm": "confirmer",
        "done": "reply_builder",
    })
    g.add_conditional_edges("confirmer", route_by_confirm, {
        "accept": "executor",
        "reject": "reply_builder",
    })
    g.add_conditional_edges("executor", route_after_exec, {
        "confirm": "confirmer",
        "wait_for_result": "clock_node",
        "reflect": "reflect",
        "done": "reply_builder",
    })
    g.add_edge("tool_worker", "parallel_merge")
    g.add_conditional_edges("parallel_merge", route_after_exec, {
        "confirm": "confirmer",
        "wait_for_result": "clock_node",
        "reflect": "reflect",
        "done": "reply_builder",
    })
    g.add_conditional_edges("reflect", route_after_reflect, {
        "replan": "planner",
        "reply": "reply_builder",
    })
    g.add_edge("clock_node", "reply_builder")
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
    """用户于对话中回复「确认/取消」时续跑 LangGraph。"""
    action_id = find_pending_confirm_action_id(session_id)
    if not action_id:
        return None
    result = resume_agent_confirm(session_id, user_id, action_id, accept)
    if not result.get("ok"):
        return [
            {"type": "assistant_message", "content": result.get("error") or "确认失败"},
            {"type": "done"},
        ]
    inner = (result.get("result") or {})
    graph_result = inner if isinstance(inner, dict) and inner.get("events") is not None else result
    events = _events_from_graph_result(graph_result if isinstance(graph_result, dict) else {})
    if not any(e.get("type") == "assistant_message" for e in events):
        msg = "已确认并继续执行。" if accept else "已取消操作。"
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
    graph = get_agent_graph()
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
        "planned_actions": [],
        "pending_high_risk": [],
        "executable_actions": [],
        "executed_results": [],
        "confirm_accept": None,
        "pending_confirm": None,
        "reply_type": "general",
        "pipeline_stage": "text_base",
        "suggestions": [],
        "next_actions": [],
        "reply": "",
        "events": [{"type": "user_message", "content": content}],
        "context_token_estimate": 0,
        "telemetry": [],
        "reflection_count": 0,
        "needs_reflection": False,
        "reflection_note": "",
        "contract_violations": [],
        "current_action": {},
        "wakeup_note": {},
        "needs_reclock": False,
    }

    config = _config(session_id)
    events: list[dict] = list(initial["events"])

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
            prompt = "请在对话中回复「确认」继续，或「取消」放弃。"
            if isinstance(payload, dict) and payload.get("summary"):
                prompt = build_dialog_confirm_prompt({
                    "tool_name": payload.get("tool"),
                    "summary": payload.get("summary"),
                    "params": {"estimated_cost": payload.get("estimatedCost") or 0},
                }, chain_cost=int(payload.get("chainEstimatedCost") or 0))
            events.append({
                "type": "assistant_message",
                "content": prompt,
                "requiresDialogConfirm": True,
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
                    prompt = "请在对话中回复「确认」继续，或「取消」放弃。"
                events.append({
                    "type": "assistant_message",
                    "content": prompt,
                    "requiresDialogConfirm": True,
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
    expected_canvas_version: int | None = None,
) -> dict:
    """从 checkpoint resume 确认。"""
    from ..core.db import SessionLocal
    from ..models import AgentAction, AgentSession
    from ..services.telemetry import agent_confirm_accept, agent_confirm_reject
    from ..tools.registry import headers_for
    import httpx

    graph = get_agent_graph()
    config = _config(session_id)

    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if not session or session.user_id != user_id:
            return {"ok": False, "error": "会话不存在"}
        record = db.get(AgentAction, action_id)
        if not record or record.session_id != session_id:
            return {"ok": False, "error": "确认记录不存在"}

        # checkpoint TTL：中断超过 5 分钟则确认失效
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
        except Exception:
            pass

        # 画布版本校验
        if session.canvas_id:
            try:
                r = httpx.get(
                    f"{settings.canvas_base_url}/internal/canvases/{session.canvas_id}/summary",
                    headers=headers_for(user_id),
                    timeout=8,
                    trust_env=False,
                )
                if r.status_code == 200:
                    current_ver = int(r.json().get("version") or 0)
                    stored = int(record.canvas_version or 0)
                    if stored and current_ver and current_ver != stored:
                        return {"ok": False, "error": "画布版本已变化，请刷新后重新发送指令",
                                "error_code": "VERSION_CONFLICT"}
            except Exception:
                pass

        if not accept:
            record.status = "cancelled"
            db.commit()
            agent_confirm_reject(session_id, record.tool_name or "")
            # 仍 resume 以结束图
            try:
                graph.invoke(Command(resume={"accept": False, "actionId": action_id}), config=config)
            except Exception:
                pass
            return {"ok": True, "cancelled": True}

        agent_confirm_accept(session_id, record.tool_name or "")
        result = graph.invoke(Command(resume={"accept": True, "actionId": action_id}), config=config)
        record.status = "executed"
        db.commit()
        return {"ok": True, "result": result if isinstance(result, dict) else {}}
    finally:
        db.close()
