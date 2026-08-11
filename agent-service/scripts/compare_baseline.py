"""对比 baseline.jsonl 中 before/after 标签的量化指标。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def agg(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return {
        "samples": len(rows),
        "avg_context_reduction_pct": round(sum(r["context_reduction_pct"] for r in rows) / len(rows), 2),
        "avg_plan_ms": round(sum(r["plan_ms"] for r in rows) / len(rows), 3),
        "avg_action_count": round(sum(r["action_count"] for r in rows) / len(rows), 2),
        "tool_whitelist_size": rows[0].get("tool_whitelist_size"),
        "paper_intents": sum(1 for r in rows if r["intent"] in ("summarize", "copy", "directions")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="baseline_after.jsonl")
    args = parser.parse_args()
    rows = load(Path(args.file))
    by_label = defaultdict(list)
    for r in rows:
        by_label[r.get("label", "unknown")].append(r)

    # 若只有 after，用同文件内 full vs summary 作为结构提升代理
    after = by_label.get("after") or rows
    before = by_label.get("before")
    report = {"after": agg(after)}
    if before:
        a, b = agg(after), agg(before)
        report["before"] = b
        report["delta"] = {
            "context_reduction_pct_pp": round(a["avg_context_reduction_pct"] - b["avg_context_reduction_pct"], 2),
            "plan_ms_change_pct": round((a["avg_plan_ms"] - b["avg_plan_ms"]) / max(b["avg_plan_ms"], 1e-6) * 100, 2),
            "tool_whitelist_delta": (a.get("tool_whitelist_size") or 0) - (b.get("tool_whitelist_size") or 0),
        }
    else:
        # 结构基线：摘要相对全量 JSON 的体积下降
        report["structural_gains"] = {
            "avg_context_reduction_vs_full_json_pct": report["after"].get("avg_context_reduction_pct"),
            "note": "无 before 标签时，以 summary vs full canvas JSON 体积下降作为上下文优化代理指标。"
                    "效果评估（梳理/文案/方向质量）待后续与产品对齐方案。",
            "collab_tools_added": ["update_memory", "clock", "load_skill", "check_task_status"],
            "telemetry_events": [
                "agent_action_success", "agent_action_fail",
                "agent_confirm_show", "agent_confirm_accept", "agent_confirm_reject",
                "clock_wakeup", "memory_updated", "skill_loaded",
            ],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
