"""AgentAction 状态机（改进计划 §12.1）。"""

from __future__ import annotations

PLANNED = "planned"
AWAITING_APPROVAL = "awaiting_approval"
APPROVED = "approved"
REJECTED = "rejected"
EXPIRED = "expired"
DISPATCHING = "dispatching"
ACCEPTED = "accepted"
WAITING_TERMINAL = "waiting_terminal"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

# 兼容历史行
LEGACY_PENDING = "pending"
LEGACY_EXECUTED = "executed"
LEGACY_CONFIRMED = "confirmed"

TERMINAL = frozenset({
    SUCCEEDED, FAILED, CANCELLED, REJECTED, EXPIRED,
    LEGACY_EXECUTED,
})

HIGH_RISK_TOOLS = frozenset({
    "submit_generation",
    "delete_nodes",
    "replace_output",
    "change_model",
    "extract_frames",
    "trim_clip",
    "upscale",
    "outpaint",
    "compose_final",
    "capture_3d_scene",
})

COSTING_TOOLS = frozenset({
    "submit_generation",
    "extract_frames",
    "trim_clip",
    "upscale",
    "outpaint",
    "compose_final",
    "capture_3d_scene",
})

REPLAYABLE_STATUSES = frozenset({
    ACCEPTED, WAITING_TERMINAL, SUCCEEDED, LEGACY_EXECUTED, DISPATCHING,
})


def is_high_risk_tool(tool_name: str) -> bool:
    return tool_name in HIGH_RISK_TOOLS
