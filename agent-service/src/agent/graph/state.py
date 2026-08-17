"""LangGraph AgentState — 贯穿整图的共享状态。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

# 单轮事件上限，防止 checkpoint 把历史 events 撑到数百 MB
_MAX_EVENTS = 120
_MAX_RESULT_CHUNKS = 80

_REPLACE_EVENTS = "__replace_events__"
_REPLACE_RESULTS = "__replace_results__"
_REPLACE_VIOLATIONS = "__replace_violations__"


def _replaceable_list_reducer(
    left: list[Any] | None,
    right: list[Any] | None,
    *,
    replace_flag: str,
    max_len: int,
) -> list[Any]:
    """operator.add 的安全替代：支持哨兵整表替换，并硬截断。

    节点必须只返回本步增量；新一轮在 input/ingest 用
    [{replace_flag: True}, ...] 丢掉 checkpoint 里的历史膨胀数据。
    """
    left_l = list(left or [])
    right_l = list(right or [])
    if right_l and isinstance(right_l[0], dict) and right_l[0].get(replace_flag):
        merged = right_l[1:]
    else:
        merged = left_l + right_l
    if len(merged) > max_len:
        merged = merged[-max_len:]
    return merged


def events_reducer(left: list | None, right: list | None) -> list:
    return _replaceable_list_reducer(
        left, right, replace_flag=_REPLACE_EVENTS, max_len=_MAX_EVENTS,
    )


def executed_results_reducer(left: list | None, right: list | None) -> list:
    return _replaceable_list_reducer(
        left, right, replace_flag=_REPLACE_RESULTS, max_len=_MAX_RESULT_CHUNKS,
    )


def contract_violations_reducer(left: list | None, right: list | None) -> list:
    return _replaceable_list_reducer(
        left, right, replace_flag=_REPLACE_VIOLATIONS, max_len=40,
    )


def reset_events(*items: dict[str, Any]) -> list[dict[str, Any]]:
    """构造「替换历史 + 本轮首批事件」载荷。"""
    return [{_REPLACE_EVENTS: True}, *[x for x in items if x]]


def reset_executed_results(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [{_REPLACE_RESULTS: True}, *[x for x in items if x]]


class PlannedActionDict(TypedDict, total=False):
    tool_name: str
    params: dict[str, Any]
    summary: str
    reasoning: str  # 这步为什么这么做（展示在「推理过程」）
    risk_level: str
    confirm_reason: str | None
    action_id: int
    status: str  # pending / ready / executed / failed / cancelled / awaiting_confirm
    step_id: str


class AgentState(TypedDict, total=False):
    # 会话标识
    session_id: int
    user_id: int
    canvas_id: int | None
    canvas_version: int
    user_content: str
    selected_nodes: list[int]

    # 上下文
    intent_type: str  # 兼容旧标签
    query_scope: str  # summary / selected / related / none
    canvas_context: dict[str, Any]
    skill_instructions: str
    skill_name: str
    recent_messages: list[dict[str, Any]]
    project_memories: list[dict[str, Any]]
    long_term_prefs: list[str]

    # ReAct 多轮（单次 turn 内 agent↔tools）
    react_mode: bool
    react_step: int
    max_react_steps: int
    react_decision: str  # act | finish | ask_user
    observations: list[dict[str, Any]]

    # 四段编排（结构化）
    run_version: int
    cancelled_run_versions: list[int]
    intent: dict[str, Any]
    selected_skill_keys: list[str]
    plan: dict[str, Any]
    pending_runs: list[dict[str, Any]]
    current_step_id: str | None
    tool_result: dict[str, Any] | None
    needs_user_input: bool
    waiting_external_event: bool
    terminal_status: str
    validation_route: str
    confirmed_action: dict[str, Any] | None
    generation_preferences: dict[str, Any]

    # 规划与执行（桥接旧 executor）
    planned_actions: list[PlannedActionDict]
    pending_high_risk: list[PlannedActionDict]
    executable_actions: list[PlannedActionDict]
    executed_results: Annotated[list[dict[str, Any]], executed_results_reducer]
    confirm_accept: bool | None
    pending_confirm: dict[str, Any] | None

    # Paper Agent 结构化输出
    reply_type: str
    pipeline_stage: str
    suggestions: list[dict[str, Any]]
    next_actions: list[str]
    reply: str

    # 循环反思
    reflection_count: int
    needs_reflection: bool
    reflection_note: str

    # 并行 Send() worker 载荷
    current_action: PlannedActionDict
    wakeup_note: dict[str, Any]
    needs_reclock: bool

    # SSE / 可观测
    # 节点只返回本步增量；新一轮用 reset_events() 丢弃 checkpoint 历史。
    events: Annotated[list[dict[str, Any]], events_reducer]
    context_token_estimate: int
    telemetry: list[dict[str, Any]]
    contract_violations: Annotated[list[dict[str, Any]], contract_violations_reducer]
