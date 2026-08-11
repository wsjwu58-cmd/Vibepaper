"""LangGraph AgentState — 贯穿整图的共享状态。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class PlannedActionDict(TypedDict, total=False):
    tool_name: str
    params: dict[str, Any]
    summary: str
    reasoning: str  # 这步为什么这么做（展示在「推理过程」）
    risk_level: str
    confirm_reason: str | None
    action_id: int
    status: str  # pending / ready / executed / failed / cancelled / awaiting_confirm


class AgentState(TypedDict):
    # 会话标识
    session_id: int
    user_id: int
    canvas_id: int | None
    canvas_version: int
    user_content: str
    selected_nodes: list[int]

    # 上下文
    intent_type: str  # summarize / copy / directions / edit / generate / query / general
    query_scope: str  # summary / selected / related / none
    canvas_context: dict[str, Any]
    skill_instructions: str
    skill_name: str
    recent_messages: list[dict[str, Any]]
    project_memories: list[dict[str, Any]]
    long_term_prefs: list[str]

    # 规划与执行
    planned_actions: list[PlannedActionDict]
    pending_high_risk: list[PlannedActionDict]
    executable_actions: list[PlannedActionDict]
    executed_results: Annotated[list[dict[str, Any]], operator.add]
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
    events: Annotated[list[dict[str, Any]], operator.add]
    context_token_estimate: int
    telemetry: list[dict[str, Any]]
    contract_violations: Annotated[list[dict[str, Any]], operator.add]
