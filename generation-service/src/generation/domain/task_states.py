"""任务状态机（PRD §5.3 / §8.3）。"""

from dataclasses import dataclass


VALID_TRANSITIONS = {
    "idle": {"queued"},
    "queued": {"running", "cancelled", "expired", "failed"},
    "running": {"succeeded", "failed", "cancelled", "settlement_error"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
    "expired": set(),
    "settlement_error": {"failed"},
}


class TaskStateError(Exception):
    pass


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> str:
    if not can_transition(current, target):
        raise TaskStateError(f"非法状态流转: {current} -> {target}")
    return target


@dataclass
class CostEstimate:
    estimated_cost: int
    pricing_version: int = 1
    breakdown: dict = None

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}
