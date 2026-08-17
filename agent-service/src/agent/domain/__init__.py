"""创作领域模型与契约校验。

子模块请直接 `from agent.domain.xxx import ...`，避免在此包级
eager import（会与 agent.planner / pipeline 形成环）。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "validate_action",
    "validate_plan",
    "audit_plan_result",
    "assert_methodology",
    "plan_advance_pipeline",
    "plan_reregenerate_stale",
    "plan_workflow_orchestration",
    "NODE_FEED_RULES",
    "WorkflowState",
    "can_feed",
    "walk_input_upstream",
    "topo_sort_executable",
    "resolve_target_context",
    "enrich_context_with_chains",
    "classify_stance",
    "merge_param_layers",
    "fill_missing",
    "apply_confirmed_action",
    "filter_actions_for_stance",
    "IntentResult",
    "PlanStep",
    "StructuredPlan",
    "classify_intent_hybrid",
    "route_intent_name",
    "SKILL_CATALOG",
    "SKILL_ROUTES",
    "catalog_summary_for_prompt",
]


def __getattr__(name: str) -> Any:
    if name in ("validate_action", "validate_plan"):
        from .creative_contract import validate_action, validate_plan
        return validate_action if name == "validate_action" else validate_plan
    if name in ("audit_plan_result", "assert_methodology"):
        from .methodology import assert_methodology, audit_plan_result
        return audit_plan_result if name == "audit_plan_result" else assert_methodology
    if name in ("plan_advance_pipeline", "plan_reregenerate_stale"):
        from .pipeline import plan_advance_pipeline, plan_reregenerate_stale
        return plan_advance_pipeline if name == "plan_advance_pipeline" else plan_reregenerate_stale
    if name in ("plan_workflow_orchestration", "NODE_FEED_RULES", "WorkflowState", "can_feed"):
        from . import workflow_orchestrator as wo
        return getattr(wo, name)
    if name in (
        "walk_input_upstream", "topo_sort_executable",
        "resolve_target_context", "enrich_context_with_chains",
    ):
        from . import dependency_graph as dg
        return getattr(dg, name)
    if name in (
        "classify_stance", "merge_param_layers", "fill_missing",
        "apply_confirmed_action", "filter_actions_for_stance",
    ):
        from . import precedence as pr
        return getattr(pr, name)
    if name in ("IntentResult", "PlanStep", "StructuredPlan"):
        from . import plan_models as pm
        return getattr(pm, name)
    if name in ("classify_intent_hybrid", "route_intent_name"):
        from . import intent_classifier as ic
        return getattr(ic, name)
    if name in ("SKILL_CATALOG", "SKILL_ROUTES", "catalog_summary_for_prompt"):
        from . import skill_catalog as sc
        return getattr(sc, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
