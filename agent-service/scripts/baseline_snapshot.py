"""Agent 优化基线快照钩子。

在重构前后运行，采集上下文体积、意图分类、工具列表等结构化指标，
供后续效果评估对比使用。

用法：
  python -m scripts.baseline_snapshot --label before|after --out baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.agent.planner import classify_intent, infer_query_scope, plan
from agent.tools.registry import TOOLS, classify_risk


SAMPLE_PROMPTS = [
    "帮我梳理这张画布",
    "写一句品牌文案",
    "给我三个创作方向",
    "创建一个图片节点",
    "删除选中节点",
    "生成10秒视频",
]


def fake_canvas(n_nodes: int = 50) -> dict:
    nodes = [{"id": i, "type": ["text", "image", "video", "audio"][i % 4], "status": "idle"}
             for i in range(1, n_nodes + 1)]
    edges = [{"id": i, "sourceNodeId": i, "targetNodeId": i + 1, "valid": True}
             for i in range(1, n_nodes)]
    return {"canvas": {"version": 1, "name": "bench"}, "nodes": nodes, "edges": edges}


def measure(label: str) -> list[dict]:
    rows = []
    for n_nodes in (10, 50, 200):
        canvas = fake_canvas(n_nodes)
        full_bytes = len(json.dumps(canvas, ensure_ascii=False))
        # 摘要裁切模拟
        summary = {
            "nodeCount": n_nodes,
            "edgeCount": n_nodes - 1,
            "nodeTypeCounts": {"text": n_nodes // 4, "image": n_nodes // 4},
            "nodes": [{"id": n["id"], "type": n["type"], "status": n["status"]} for n in canvas["nodes"][:20]],
        }
        summary_bytes = len(json.dumps(summary, ensure_ascii=False))
        for prompt in SAMPLE_PROMPTS:
            intent = classify_intent(prompt)
            scope = infer_query_scope(intent)
            t0 = time.perf_counter()
            actions = plan(prompt, summary, [1, 2])
            elapsed_ms = (time.perf_counter() - t0) * 1000
            risks = [classify_risk(a.tool_name, a.params, summary)[0] for a in actions]
            rows.append({
                "label": label,
                "ts": datetime.now(timezone.utc).isoformat(),
                "prompt": prompt,
                "intent": intent,
                "query_scope": scope,
                "canvas_nodes": n_nodes,
                "full_context_bytes": full_bytes,
                "summary_context_bytes": summary_bytes,
                "context_reduction_pct": round((1 - summary_bytes / full_bytes) * 100, 2),
                "action_count": len(actions),
                "tools": [a.tool_name for a in actions],
                "risks": risks,
                "plan_ms": round(elapsed_ms, 3),
                "tool_whitelist_size": len(TOOLS),
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="after")
    parser.add_argument("--out", default="baseline.jsonl")
    args = parser.parse_args()
    rows = measure(args.label)
    path = Path(args.out)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # 汇总
    reductions = [r["context_reduction_pct"] for r in rows]
    print(json.dumps({
        "label": args.label,
        "samples": len(rows),
        "avg_context_reduction_pct": round(sum(reductions) / len(reductions), 2),
        "tool_count": len(TOOLS),
        "out": str(path.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
