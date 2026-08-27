"""executor：执行白名单工具，结果回写消息，exec 统一 ack。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from ...core.config import settings
from ...core.db import SessionLocal
from ...domain.action_states import WAITING_TERMINAL
from ...domain.idempotency import derive_idempotency_key
from ...models import AgentAction, AgentMessage, AgentSession
from ...services.telemetry import agent_action_fail, agent_action_success
from ...tools.registry import TOOLS, _coerce_node_id, headers_for
from ..state import AgentState
from .risk_classifier import _next_id

logger = logging.getLogger("agent.graph.executor")

EXEC_TOOLS = {
    "submit_generation", "extract_frames", "trim_clip", "upscale", "outpaint", "compose_final", "capture_3d_scene",
}


def _resolve_node_ref(value, created_ids: list[int], last_id: int | None) -> int | None:
    """解析 $created[0] / $last 等占位符为真实节点 ID。"""
    if value is None:
        return last_id
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", ""}:
        return last_id
    if text in ("$last", "$created[-1]"):
        return created_ids[-1] if created_ids else last_id
    if text in ("$first", "$created[0]"):
        return created_ids[0] if created_ids else last_id
    m = re.match(r"^\$created\[(\d+)\]$", text)
    if m:
        idx = int(m.group(1))
        if 0 <= idx < len(created_ids):
            return created_ids[idx]
        return last_id
    return _coerce_node_id(value)


def _query_existing_task(node_id: int, user_id: int) -> dict | None:
    try:
        r = httpx.get(
            f"{settings.billing_base_url}/api/v1/tasks",
            headers=headers_for(user_id),
            params={"nodeId": node_id, "status": "queued,running", "limit": 1},
            timeout=8,
            trust_env=False,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("items") or data.get("tasks") or []
        return items[0] if items else None
    except Exception as e:
        logger.debug("task status probe failed: %s", e)
        return None


def _write_result_message(db, session_id: int, tool: str, ok: bool, data: dict):
    db.add(AgentMessage(
        id=_next_id(),
        session_id=session_id,
        role="assistant",
        msg_type="result" if ok else "error",
        content=f"{tool}: {'ok' if ok else 'error'}",
        meta={"tool": tool, "ok": ok, "data": data},
        created_at=datetime.now(timezone.utc),
    ))


def _call_tool(tool, canvas_id, user_id, params: dict, *, extra: dict | None = None) -> dict:
    kwargs = dict(params or {})
    kwargs.pop("canvas_id", None)
    if extra:
        kwargs.update(extra)
    try:
        return tool.fn(canvas_id=canvas_id, user_id=user_id, **kwargs)
    except TypeError:
        # 部分工具不收 canvas_id
        try:
            return tool.fn(user_id=user_id, **kwargs)
        except TypeError:
            return tool.fn(user_id=user_id, canvas_id=canvas_id, **kwargs)


def executor_node(state: AgentState) -> dict:
    # executed_results / events 均为 operator.add：只收集本节点新增项
    results: list[dict] = []
    events: list[dict] = []
    user_id = state["user_id"]
    canvas_id = state.get("canvas_id")
    canvas_version = int(state.get("canvas_version") or 1)
    last_created_node_id = None
    created_node_ids: list[int] = []

    db = SessionLocal()
    try:
        for action in state.get("executable_actions") or []:
            tool_name = action["tool_name"]
            params = dict(action.get("params") or {})
            action_id = int(action.get("action_id") or _next_id())
            summary = action.get("summary") or tool_name

            from ...tools.registry import normalize_tool_params
            params = normalize_tool_params(tool_name, params)

            # create / update / submit：解析占位符并注入新建节点 ID
            if tool_name in EXEC_TOOLS or tool_name in (
                "submit_generation", "update_node_config", "change_model", "replace_output",
            ):
                raw_nid = params.get("node_id") or params.get("nodeId")
                resolved = _resolve_node_ref(raw_nid, created_node_ids, last_created_node_id)
                if resolved:
                    params["node_id"] = resolved
                elif raw_nid is None and last_created_node_id and tool_name == "update_node_config":
                    params["node_id"] = last_created_node_id
            if tool_name == "connect_nodes":
                edges = list(params.get("edges") or [])
                fixed = []
                for e in edges:
                    ee = dict(e)
                    src = _resolve_node_ref(
                        ee.get("sourceNodeId") if ee.get("sourceNodeId") is not None else ee.get("source"),
                        created_node_ids, last_created_node_id,
                    )
                    tgt = _resolve_node_ref(
                        ee.get("targetNodeId") if ee.get("targetNodeId") is not None else ee.get("target"),
                        created_node_ids, last_created_node_id,
                    )
                    if src and tgt:
                        ee["sourceNodeId"] = src
                        ee["targetNodeId"] = tgt
                        fixed.append(ee)
                if fixed:
                    params["edges"] = fixed
                elif state.get("selected_nodes") and last_created_node_id:
                    params["edges"] = [{
                        "sourceNodeId": state["selected_nodes"][0],
                        "targetNodeId": last_created_node_id,
                        "dependencyType": "input",
                    }]

            record = db.get(AgentAction, action_id)
            if record is None:
                record = AgentAction(
                    id=action_id,
                    session_id=state["session_id"],
                    user_id=user_id,
                    action_type=tool_name,
                    tool_name=tool_name,
                    params=params,
                    risk_level=action.get("risk_level") or "low",
                    confirm_reason=action.get("confirm_reason"),
                    status="pending",
                    canvas_version=canvas_version,
                    plan_version=int((state.get("plan") or {}).get("version") or state.get("run_version") or 1),
                    step_id=action.get("step_id"),
                    idempotency_key=derive_idempotency_key(action_id, 1),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(record)
                db.flush()
            elif not record.idempotency_key:
                record.idempotency_key = derive_idempotency_key(record.id, record.attempt_no or 1)

            if tool_name in EXEC_TOOLS or tool_name == "submit_generation":
                node_id = params.get("node_id") or params.get("nodeId")
                # 占位符未解析（常见于确认后二次执行）：友好失败，禁止 int('$created[0]')
                if node_id is not None and str(node_id).strip().startswith("$"):
                    data = {
                        "error": "节点尚未创建完成，无法提交生成。请重试或先确认画布上已有对应节点。",
                        "error_code": "INVALID_INPUT",
                    }
                    record.status = "failed"
                    record.error_code = "INVALID_INPUT"
                    record.result = data
                    _write_result_message(db, state["session_id"], tool_name, False, data)
                    db.commit()
                    results.append({"tool": tool_name, "ok": False, "data": data, "summary": summary})
                    events.append({"type": "action_result", "actionId": action_id,
                                   "tool": tool_name, "ok": False, "data": data})
                    agent_action_fail(state["session_id"], tool_name, error_code="INVALID_INPUT")
                    continue
                coerced = _coerce_node_id(node_id)
                if tool_name in EXEC_TOOLS and coerced:
                    existing = _query_existing_task(coerced, user_id)
                    if existing and existing.get("status") in ("queued", "running"):
                        data = {
                            "ack": True,
                            "task_id": existing.get("id") or existing.get("taskId"),
                            "status": existing["status"],
                            "note": "任务已在队列中，未重复提交",
                            "node_id": coerced,
                        }
                        record.status = WAITING_TERMINAL
                        record.task_id = str(data["task_id"])
                        record.result = data
                        _write_result_message(db, state["session_id"], tool_name, True, data)
                        db.commit()
                        results.append({"tool": tool_name, "ok": True, "summary": summary, **data})
                        events.append({"type": "action_result", "actionId": action_id,
                                       "tool": tool_name, "ok": True, "data": data})
                        agent_action_success(state["session_id"], tool_name, 1)
                        continue
                if coerced:
                    params["node_id"] = coerced

            if not canvas_id and tool_name not in (
                "list_models", "search_assets", "update_memory", "clock", "load_skill", "check_task_status",
            ):
                data = {"error": "缺少画布 ID（canvasId）。请在画布页打开 Agent 后重试。", "error_code": "INVALID_INPUT"}
                record.status = "failed"
                record.error_code = "INVALID_INPUT"
                record.result = data
                _write_result_message(db, state["session_id"], tool_name, False, data)
                db.commit()
                results.append({"tool": tool_name, "ok": False, "data": data})
                events.append({"type": "action_result", "actionId": action_id,
                               "tool": tool_name, "ok": False, "data": data})
                agent_action_fail(state["session_id"], tool_name, error_code="INVALID_INPUT")
                continue

            tool = TOOLS.get(tool_name)
            if not tool:
                data = {"error": "unknown tool"}
                record.status = "failed"
                record.error_code = "TOOL_ERROR"
                record.result = data
                _write_result_message(db, state["session_id"], tool_name, False, data)
                db.commit()
                results.append({"tool": tool_name, "ok": False, "data": data})
                events.append({"type": "action_result", "actionId": action_id,
                               "tool": tool_name, "ok": False, "data": data})
                agent_action_fail(state["session_id"], tool_name)
                continue

            try:
                from ...domain.creative_contract import validate_action as _validate_contract
                contract_err = _validate_contract(
                    {"tool_name": tool_name, "params": params},
                    state.get("canvas_context"),
                )
                if contract_err:
                    data = {"error": contract_err, "error_code": "CONTRACT_VIOLATION"}
                    record.status = "failed"
                    record.error_code = "CONTRACT_VIOLATION"
                    record.result = data
                    _write_result_message(db, state["session_id"], tool_name, False, data)
                    db.commit()
                    results.append({"tool": tool_name, "ok": False, "data": data})
                    events.append({"type": "action_result", "actionId": action_id,
                                   "tool": tool_name, "ok": False, "data": data})
                    agent_action_fail(state["session_id"], tool_name, error_code="CONTRACT_VIOLATION")
                    continue

                if tool_name == "connect_nodes" and canvas_id:
                    from ...services.session_service import session_service
                    cleaned = session_service.resolve_edges(db, canvas_id, params.get("edges", []))
                    if not cleaned:
                        data = {"error": "连线缺少有效的 source/target 节点 ID", "error_code": "INVALID_INPUT"}
                        record.status = "failed"
                        record.error_code = "INVALID_INPUT"
                        record.result = data
                        _write_result_message(db, state["session_id"], tool_name, False, data)
                        db.commit()
                        results.append({"tool": tool_name, "ok": False, "data": data})
                        events.append({"type": "action_result", "actionId": action_id,
                                       "tool": tool_name, "ok": False, "data": data})
                        agent_action_fail(state["session_id"], tool_name, error_code="INVALID_INPUT")
                        continue
                    params["edges"] = cleaned

                tool_extra = {}
                if tool_name == "create_nodes":
                    tool_extra["user_content"] = state.get("user_content") or ""
                if tool_name in EXEC_TOOLS:
                    tool_extra["agent_action_id"] = action_id
                    tool_extra["idempotency_key"] = record.idempotency_key
                data = _call_tool(tool, canvas_id, user_id, params, extra=tool_extra)
                ok = "error" not in data
                if ok and tool_name == "create_nodes":
                    created = data.get("createdNodes") or data.get("nodes") or []
                    for c in created:
                        nid = c.get("id") or c.get("nodeId")
                        if nid:
                            try:
                                created_node_ids.append(int(nid))
                            except (TypeError, ValueError):
                                pass
                    if created_node_ids:
                        last_created_node_id = created_node_ids[-1]
                if ok and tool_name in ("create_nodes", "connect_nodes"):
                    events.append({
                        "type": "canvas_changed",
                        "tool": tool_name,
                        "data": data,
                    })
                if tool_name in EXEC_TOOLS and ok:
                    task_id = data.get("taskId") or data.get("id") or data.get("task_id")
                    data = {
                        **data,
                        "ack": True,
                        "task_id": task_id,
                        "status": data.get("status") or "queued",
                        "estimatedCost": data.get("estimatedCost") or params.get("estimated_cost"),
                        "node_id": params.get("node_id"),
                        "model_type": params.get("model_type"),
                    }
                if ok and tool_name in EXEC_TOOLS and data.get("task_id"):
                    record.status = WAITING_TERMINAL
                    record.task_id = str(data["task_id"])
                else:
                    record.status = "executed" if ok else "failed"
                record.result = data
                record.error_code = None if ok else "TOOL_ERROR"
                if tool_name in EXEC_TOOLS and ok:
                    cost = int(data.get("estimatedCost") or 0)
                    if cost:
                        session = db.get(AgentSession, state["session_id"])
                        if session:
                            session.points_used_total = (session.points_used_total or 0) + cost
                _write_result_message(db, state["session_id"], tool_name, ok, data)
                db.commit()
                entry = {"tool": tool_name, "ok": ok, "data": data, "summary": summary}
                if state.get("react_mode"):
                    entry["react_step"] = int(state.get("react_step") or 0)
                if data.get("ack"):
                    entry.update({
                        "ack": True,
                        "task_id": data.get("task_id"),
                        "node_id": data.get("node_id"),
                        "model_type": data.get("model_type"),
                    })
                if data.get("workflow_notes"):
                    entry["workflow_notes"] = data["workflow_notes"]
                results.append(entry)
                events.append({"type": "action_result", "actionId": action_id,
                               "tool": tool_name, "ok": ok, "data": data})
                if ok:
                    affected = len(data.get("createdNodes") or data.get("deleted") or [1])
                    agent_action_success(state["session_id"], tool_name, affected)
                else:
                    agent_action_fail(state["session_id"], tool_name)
            except Exception as e:
                data = {"error": str(e)[:300]}
                record.status = "failed"
                record.error_code = "TOOL_ERROR"
                record.result = data
                _write_result_message(db, state["session_id"], tool_name, False, data)
                db.commit()
                results.append({"tool": tool_name, "ok": False, "data": data})
                events.append({"type": "action_result", "actionId": action_id,
                               "tool": tool_name, "ok": False, "data": data})
                agent_action_fail(state["session_id"], tool_name)
    finally:
        db.close()

    out: dict = {
        "executed_results": results,
        "executable_actions": [],
        "events": events,
    }

    # ReAct 观察：供下一拍 Thought 引用（含步号，便于失败回环）
    if state.get("react_mode"):
        prev_obs = list(state.get("observations") or [])
        step_n = int(state.get("react_step") or 0)
        for r in results:
            data = r.get("data") if isinstance(r.get("data"), dict) else {}
            prev_obs.append({
                "react_step": r.get("react_step", step_n),
                "tool": r.get("tool"),
                "ok": r.get("ok"),
                "summary": r.get("summary") or "",
                "error": data.get("error") or data.get("error_code"),
                "data": data,
            })
        out["observations"] = prev_obs[-12:]
        # 本拍失败时打标，方便前端/下一拍感知
        beat_fails = [r for r in results if not r.get("ok")]
        if beat_fails:
            events.append({
                "type": "react_observation",
                "step": step_n,
                "ok": False,
                "failures": [
                    {"tool": r.get("tool"), "error": (r.get("data") or {}).get("error")}
                    for r in beat_fails
                ],
            })
            out["events"] = events

    # load_skill：把规则累加进 state，下一拍立刻可用
    skill_keys = list(state.get("selected_skill_keys") or [])
    skill_text = state.get("skill_instructions") or ""
    skill_changed = False
    for r in results:
        if r.get("tool") != "load_skill" or not r.get("ok"):
            continue
        data = r.get("data") if isinstance(r.get("data"), dict) else {}
        instr = str(data.get("instructions") or "").strip()
        loaded = list(data.get("loaded_keys") or [])
        sk = str(data.get("skill_key") or "")
        if sk and sk not in loaded:
            loaded = [sk] + loaded
        for k in loaded:
            if k and k not in skill_keys:
                skill_keys.append(k)
                skill_changed = True
        if instr:
            block = f"\n\n## Skill: {data.get('name') or sk}\n{instr}"
            if block.strip() not in skill_text:
                skill_text = (skill_text + block).strip()
                # 长度上限：保留尾部
                if len(skill_text) > 12000:
                    skill_text = skill_text[-12000:]
                skill_changed = True
            events.append({
                "type": "skill_loaded",
                "skill": data.get("name") or sk,
                "keys": loaded or ([sk] if sk else []),
            })
    if skill_changed:
        out["selected_skill_keys"] = skill_keys
        out["skill_instructions"] = skill_text
        out["skill_name"] = "+".join(skill_keys) if skill_keys else state.get("skill_name")

    # 把本轮新建节点 ID 写回待确认动作，解析 $created[N] / 空 node_id
    # （确认后二次执行时 created_ids 已不在作用域，必须在这里固化）
    if created_node_ids or last_created_node_id:
        pending = list(state.get("pending_high_risk") or [])
        new_pending = []
        patched = False
        for a in pending:
            params = dict(a.get("params") or {})
            tool = a.get("tool_name") or ""
            changed = False
            if tool in EXEC_TOOLS or tool == "submit_generation":
                raw = params.get("node_id") if params.get("node_id") is not None else params.get("nodeId")
                resolved = _resolve_node_ref(raw, created_node_ids, last_created_node_id)
                if resolved and resolved != raw:
                    params["node_id"] = resolved
                    changed = True
            if tool == "connect_nodes":
                edges = list(params.get("edges") or [])
                fixed = []
                edge_changed = False
                for e in edges:
                    ee = dict(e)
                    src = _resolve_node_ref(
                        ee.get("sourceNodeId") if ee.get("sourceNodeId") is not None else ee.get("source"),
                        created_node_ids, last_created_node_id,
                    )
                    tgt = _resolve_node_ref(
                        ee.get("targetNodeId") if ee.get("targetNodeId") is not None else ee.get("target"),
                        created_node_ids, last_created_node_id,
                    )
                    if src and tgt:
                        if src != ee.get("sourceNodeId") or tgt != ee.get("targetNodeId"):
                            edge_changed = True
                        ee["sourceNodeId"] = src
                        ee["targetNodeId"] = tgt
                        fixed.append(ee)
                if edge_changed and fixed:
                    params["edges"] = fixed
                    changed = True
            if changed:
                patched = True
                new_pending.append({**a, "params": params})
            else:
                new_pending.append(a)
        if patched:
            out["pending_high_risk"] = new_pending
    return out
