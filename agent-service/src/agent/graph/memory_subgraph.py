"""记忆 LangGraph 子图：去重 → 合并 → 压缩。"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..core.db import SessionLocal
from ..services.memory_service import memory_service
from ..services.telemetry import memory_updated

logger = logging.getLogger("agent.graph.memory")


class MemoryTaskState(TypedDict, total=False):
    task: dict[str, Any]
    deduped: bool
    merged: bool
    compressed: bool
    ok: bool
    error: str | None


def _dedupe_node(state: MemoryTaskState) -> dict:
    """语义去重标记（实际比对在 merge）。"""
    return {"deduped": True}


def _merge_node(state: MemoryTaskState) -> dict:
    task = state.get("task") or {}
    db = SessionLocal()
    try:
        memory_service.process_memory_update(db, task)
        memory_updated(task.get("user_id", 0), task.get("scope", ""))
        return {"merged": True, "ok": True}
    except Exception as e:
        logger.exception("memory subgraph merge failed")
        return {"merged": False, "ok": False, "error": str(e)[:200]}
    finally:
        db.close()


def _compress_node(state: MemoryTaskState) -> dict:
    """压缩已在 process_memory_update 内触发，此处标记完成。"""
    return {"compressed": True}


def build_memory_subgraph():
    g = StateGraph(MemoryTaskState)
    g.add_node("dedupe", _dedupe_node)
    g.add_node("merge", _merge_node)
    g.add_node("compress", _compress_node)
    g.add_edge(START, "dedupe")
    g.add_edge("dedupe", "merge")
    g.add_edge("merge", "compress")
    g.add_edge("compress", END)
    return g.compile()


_memory_graph = None


def run_memory_subgraph(task: dict) -> dict:
    global _memory_graph
    if _memory_graph is None:
        _memory_graph = build_memory_subgraph()
    return _memory_graph.invoke({"task": task})
