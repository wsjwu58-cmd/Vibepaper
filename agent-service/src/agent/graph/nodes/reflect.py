"""reflect：执行后循环反思，必要时重规划。"""

from __future__ import annotations

from ..state import AgentState

MAX_REFLECTIONS = 2


def reflect_node(state: AgentState) -> dict:
    results = state.get("executed_results") or []
    count = int(state.get("reflection_count") or 0)
    failures = [r for r in results if not r.get("ok")]
    contract_blocked = [r for r in results if (r.get("data") or {}).get("error_code") == "CONTRACT_VIOLATION"]
    setup_ok = any(
        r.get("ok") and r.get("tool") in ("create_nodes", "connect_nodes", "get_selected_nodes")
        for r in results
    )
    submit_failures = [r for r in failures if r.get("tool") == "submit_generation"]

    needs = False
    notes: list[str] = []

    if failures:
        # 节点已建好仅提交失败时，不重跑整条 pipeline
        if setup_ok and submit_failures and len(failures) == len(submit_failures):
            needs = False
            notes.append("提交生成失败，可调整 Prompt 或模型后重试")
        else:
            needs = True
            notes.append(f"{len(failures)} 个工具执行失败，尝试调整计划")
    if contract_blocked:
        needs = True
        notes.append("创作契约校验未通过，需补充分镜/关键帧后再生成")
    # 多步 pipeline 且仍有 pending 非 exec 动作时不反思
    if count >= MAX_REFLECTIONS:
        needs = False
        notes.append("已达最大反思次数")

    reflection_note = "；".join(notes) if notes else ""
    return {
        "needs_reflection": needs and count < MAX_REFLECTIONS,
        "reflection_count": count + (1 if needs and count < MAX_REFLECTIONS else 0),
        "reflection_note": reflection_note,
        # 清空待执行以便 planner 重规划
        "planned_actions": [] if needs and count < MAX_REFLECTIONS else state.get("planned_actions"),
        "executable_actions": [],
        "pending_high_risk": [],
    }
