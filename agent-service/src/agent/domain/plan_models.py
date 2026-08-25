"""四段编排的结构化计划模型（意图 / 步骤 / 待唤醒）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

IntentName = Literal[
    "discussion",
    "direct_canvas_action",
    "workflow_orchestration",
    "advance_pipeline",
    "regenerate_stale",
    "edit_existing",
    "unknown",
]

StepKind = Literal[
    "read",
    "query",
    "load_skill",
    "ask_user",
    "edit",
    "exec",
    "respond",
]

StepStatus = Literal[
    "planned",
    "ready",
    "running",
    "queued",
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
]

TerminalStatus = Literal[
    "running",
    "waiting_user",
    "waiting_external",
    "completed",
    "failed",
    "cancelled",
]


class IntentResult(BaseModel):
    name: IntentName = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    wants_execution: bool = False
    requested_skill: Optional[str] = None
    target_description: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    id: str
    kind: StepKind
    title: str
    purpose: str = ""
    depends_on: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = "planned"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None


def normalize_next_actions(raw: Any) -> list[str]:
    """把 LLM 偶发塞进 next_actions 的动作 dict 压成可点击短句。"""
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for item in items:
        text = _next_action_to_str(item)
        if text and text not in out:
            out.append(text)
        if len(out) >= 8:
            break
    return out


def _next_action_to_str(item: Any) -> str | None:
    if item is None:
        return None
    if isinstance(item, str):
        s = item.strip()
        return s or None
    if isinstance(item, dict):
        for key in ("title", "summary", "label", "text", "reply", "content", "purpose"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:80]
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        for key in ("prompt", "title", "summary"):
            val = params.get(key) if params else None
            if isinstance(val, str) and val.strip():
                return val.strip()[:60]
        tool = item.get("tool") or item.get("tool_name") or item.get("type")
        if isinstance(tool, str) and tool.strip():
            return tool.strip()[:40]
        return None
    s = str(item).strip()
    return s or None


def extract_misplaced_actions(raw_next: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """从 next_actions 中拆出误放的工具动作，剩余压成短句。"""
    if not isinstance(raw_next, list):
        return normalize_next_actions(raw_next), []
    chips: list[str] = []
    actions: list[dict[str, Any]] = []
    for item in raw_next:
        if isinstance(item, dict) and _looks_like_action(item):
            actions.append(_coerce_action_dict(item))
            continue
        text = _next_action_to_str(item)
        if text and text not in chips:
            chips.append(text)
    return chips[:8], actions


def _looks_like_action(item: dict[str, Any]) -> bool:
    if item.get("tool") or item.get("tool_name"):
        return True
    t = str(item.get("type") or "").strip().lower()
    return t in {
        "create_node", "create_nodes", "connect_nodes", "update_node_config",
        "layout_nodes", "delete_nodes", "submit_generation", "compose_final",
        "load_skill", "extract_frames", "trim_clip", "upscale", "outpaint",
    }


def _coerce_action_dict(item: dict[str, Any]) -> dict[str, Any]:
    tool = str(item.get("tool") or item.get("tool_name") or "").strip()
    if not tool:
        legacy = str(item.get("type") or "").strip()
        if legacy == "create_node":
            tool = "create_nodes"
            node = {k: v for k, v in item.items() if k not in {"type", "tool", "tool_name", "summary", "reasoning", "params"}}
            params = dict(item.get("params") or {})
            if node and "nodes" not in params:
                params = {"nodes": [node], **params}
            return {
                "tool": tool,
                "params": params,
                "summary": str(item.get("summary") or "创建节点"),
                "reasoning": str(item.get("reasoning") or ""),
            }
        tool = legacy
    return {
        "tool": tool,
        "params": dict(item.get("params") or {}),
        "summary": str(item.get("summary") or tool),
        "reasoning": str(item.get("reasoning") or ""),
    }


class StructuredPlan(BaseModel):
    """创意 + 执行编译后的完整计划（画布真相源之上的任务图）。"""

    goal: str = ""
    workflow: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlanStep] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    user_decision_required: bool = False
    reply: str = ""
    thinking: str = ""
    next_actions: list[str] = Field(default_factory=list)

    @field_validator("next_actions", mode="before")
    @classmethod
    def _coerce_next_actions(cls, value: Any) -> list[str]:
        return normalize_next_actions(value)


class PendingRun(BaseModel):
    step_id: str
    target: Optional[str] = None
    expected_terminal_states: list[str] = Field(
        default_factory=lambda: ["ready", "failed", "aborted", "succeeded", "success"],
    )
    run_version: int = 0


def get_ready_steps(plan: StructuredPlan) -> list[PlanStep]:
    status_map = {s.id: s.status for s in plan.steps}
    return [
        step
        for step in plan.steps
        if step.status == "planned"
        and all(status_map.get(dep) == "succeeded" for dep in step.depends_on)
    ]


def mark_step(
    plan: StructuredPlan,
    step_id: str,
    status: StepStatus,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> StructuredPlan:
    steps = []
    for s in plan.steps:
        if s.id == step_id:
            data = s.model_dump()
            data["status"] = status
            if result is not None:
                data["result"] = result
            if error is not None:
                data["error"] = error
            steps.append(PlanStep(**data))
        else:
            steps.append(s)
    return plan.model_copy(update={"steps": steps})


def is_task_complete(plan: StructuredPlan | None, pending_runs: list[PendingRun] | None) -> bool:
    if not plan:
        return False
    active = {"planned", "ready", "running", "queued", "blocked"}
    if any(s.status in active for s in plan.steps):
        return False
    if pending_runs:
        return False
    if any(s.status == "failed" for s in plan.steps):
        return False
    return True


def plan_to_dict(plan: StructuredPlan | None) -> dict[str, Any] | None:
    return plan.model_dump() if plan else None


def plan_from_dict(data: dict[str, Any] | None) -> StructuredPlan | None:
    if not data:
        return None
    return StructuredPlan.model_validate(data)


def intent_from_dict(data: dict[str, Any] | None) -> IntentResult:
    if not data:
        return IntentResult()
    return IntentResult.model_validate(data)
