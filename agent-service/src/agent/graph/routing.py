"""条件路由：风险分流 / 确认结果 / exec 后唤醒 / 并行 Send / 反思。"""

from __future__ import annotations

from langgraph.types import Send

from ..tools.registry import TOOLS
from .state import AgentState

READ_PARALLEL_MIN = 2


def route_by_risk(state: AgentState) -> str | list[Send]:
    executable = state.get("executable_actions") or []
    pending = state.get("pending_high_risk") or []
    # 有低风险写操作时先执行（如 create_nodes），再进入确认
    if executable and pending:
        write_or_mixed = [
            a for a in executable
            if not (TOOLS.get(a["tool_name"]) and TOOLS[a["tool_name"]].risk_level == "read")
        ]
        if write_or_mixed:
            return "execute"
    if pending:
        return "confirm"
    if not executable:
        return "done"
    read_only = [
        a for a in executable
        if TOOLS.get(a["tool_name"]) and TOOLS[a["tool_name"]].risk_level == "read"
        and a["tool_name"] not in ("update_memory",)
    ]
    write_actions = [a for a in executable if a not in read_only]
    if len(read_only) >= READ_PARALLEL_MIN and not write_actions:
        return [
            Send("tool_worker", {**state, "current_action": a, "executable_actions": []})
            for a in read_only
        ]
    if executable:
        return "execute"
    return "done"


def route_by_confirm(state: AgentState) -> str:
    if state.get("confirm_accept") is True and state.get("executable_actions"):
        return "accept"
    return "reject"


def route_after_exec(state: AgentState) -> str:
    if state.get("pending_high_risk"):
        return "confirm"

    results = list(state.get("executed_results") or [])
    for result in results:
        if result.get("ack") and result.get("task_id"):
            return "wait_for_result"
    failures = [r for r in results if not r.get("ok")]
    blocked = state.get("contract_violations") or []
    count = int(state.get("reflection_count") or 0)
    if (failures or blocked) and count < 2:
        return "reflect"
    if (
        state.get("react_mode")
        and str(state.get("react_decision") or "") == "act"
        and int(state.get("react_step") or 0) < int(state.get("max_react_steps") or 8)
    ):
        return "continue"
    return "done"


def route_after_reflect(state: AgentState) -> str:
    if state.get("needs_reflection"):
        return "replan"
    return "reply"


def route_after_check_status(state: AgentState) -> str:
    if state.get("needs_reclock"):
        return "reclock"
    for result in state.get("executed_results") or []:
        if result.get("ack") and result.get("task_id"):
            return "reclock"
    return "reply"
