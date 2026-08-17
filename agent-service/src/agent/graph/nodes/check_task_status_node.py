"""check_task_status_node：clock 唤醒图入口 + 依赖就绪时自动 submit 下游。"""

from __future__ import annotations

import logging

import httpx

from ...core.config import settings
from ...domain.dependency_scheduler import plan_downstream_submits
from ...tools.registry import TOOLS, headers_for
from ..state import AgentState

logger = logging.getLogger("agent.check_task_status")


def _fetch_canvas_context(user_id: int, canvas_id: int | None) -> dict:
    if not canvas_id:
        return {}
    tool = TOOLS.get("get_canvas_summary")
    if tool:
        try:
            data = tool.fn(canvas_id=canvas_id, user_id=user_id)
            if isinstance(data, dict) and "error" not in data:
                return data
        except Exception:
            pass
    try:
        r = httpx.get(
            f"{settings.canvas_base_url}/internal/canvases/{canvas_id}",
            headers=headers_for(user_id),
            timeout=10,
            trust_env=False,
        )
        if r.status_code == 200:
            raw = r.json()
            return {
                "nodes": raw.get("nodes") or [],
                "edges": raw.get("edges") or [],
                "canvasId": canvas_id,
            }
    except Exception as exc:
        logger.debug("fetch canvas failed: %s", exc)
    return {}


def _execute_downstream_submits(
    state: AgentState,
    canvas_context: dict,
    completed_node_id: int | None,
) -> tuple[list[dict], list[str], bool]:
    """执行依赖就绪的下游 submit，返回 (executed_results, labels, needs_reclock)。"""
    user_id = int(state["user_id"])
    canvas_id = state.get("canvas_id")
    actions = plan_downstream_submits(canvas_context, completed_node_id)
    if not actions:
        return [], [], False

    results: list[dict] = []
    labels: list[str] = []
    needs_reclock = False

    for action in actions:
        tool_name = action.tool_name
        tool = TOOLS.get(tool_name)
        if not tool:
            continue
        params = dict(action.params or {})
        try:
            data = tool.fn(
                user_id=user_id,
                canvas_id=canvas_id,
                **params,
            )
        except Exception as exc:
            data = {"error": str(exc)[:200]}
        ok = "error" not in (data or {})
        ack = ok and bool(data.get("task_id") or data.get("taskId"))
        if ack:
            needs_reclock = True
        results.append({
            "tool": tool_name,
            "ok": ok,
            "data": data,
            "ack": ack,
            "task_id": data.get("task_id") or data.get("taskId"),
            "node_id": params.get("node_id"),
            "model_type": params.get("model_type"),
            "summary": action.summary,
        })
        if ok:
            labels.append(action.summary or tool_name)
        else:
            logger.warning("downstream submit failed: %s %s", tool_name, data)

    return results, labels, needs_reclock


_TASK_ERROR_TEXT = {
    "INSUFFICIENT_POINTS": "点数不足，请先充值",
    "CONTENT_BLOCKED": "内容未通过安全审核，建议调整画面描述",
    "MODEL_TIMEOUT": "模型响应超时，建议稍后重试",
    "MODEL_UNAVAILABLE": "模型暂不可用，可换模型再试",
    "FREEZE_EXPIRED": "点数冻结已过期，请重新提交",
    "INVALID_INPUT": "生成参数不完整，建议调整 Prompt 后重试",
}


def _humanize_task_error(result: dict) -> str:
    """把任务错误码翻成用户可读原因，不暴露 task id 等内部细节。"""
    code = str(result.get("error_code") or result.get("errorCode") or "").upper()
    if code in _TASK_ERROR_TEXT:
        return _TASK_ERROR_TEXT[code]
    msg = str(
        result.get("error_message")
        or result.get("errorMessage")
        or result.get("error")
        or result.get("message")
        or ""
    ).strip()
    # Seedance 误用于合成时的典型报错 → 人话
    if "task_type" in msg and "r2v" in msg:
        return "合成应使用本地拼接模型，而不是视频生成模型；请点「合成」重试"
    return msg[:80] if msg else "原因未知"


def _node_title(canvas_ctx: dict, node_id) -> str:
    """从画布上下文取节点标题；拿不到就给中性称呼，不暴露节点 id。"""
    if node_id is not None:
        for n in canvas_ctx.get("nodes") or []:
            if int(n.get("id") or 0) == int(node_id):
                return str((n.get("params") or {}).get("title") or n.get("title") or "当前节点")
    return "当前节点"


def check_task_status_node(state: AgentState) -> dict:
    note = state.get("wakeup_note") or {}
    user_id = int(state["user_id"])
    canvas_id = note.get("canvas_id") or state.get("canvas_id")
    task_id = note.get("task_id")
    node_id = note.get("node_id")

    tool = TOOLS.get("check_task_status")
    if not tool:
        return {"events": [{"type": "task_status", "data": {"error": "tool missing"}}]}

    result = tool.fn(
        user_id=user_id,
        canvas_id=canvas_id,
        task_id=task_id,
        node_id=node_id,
        note=note,
    )
    status = str(result.get("status") or "unknown")
    fetch_failed = "error" in result and status in ("fetch_error", "unknown", "")
    events: list[dict] = [{
        "type": "task_status",
        "silent": status in ("queued", "running"),
        "data": result,
    }]

    reply = ""
    reply_type = "task_status"
    next_actions: list[str] = []
    executed_results = [{
        "tool": "check_task_status",
        # 任务失败仍算查询成功；只有 HTTP 取数失败才 ok=False
        "ok": not fetch_failed,
        "data": result,
        "ack": status in ("queued", "running"),
        "task_id": result.get("task_id"),
        "node_id": node_id,
        "model_type": note.get("model_type"),
    }]
    needs_reclock = status in ("queued", "running")

    if fetch_failed:
        return {
            "executed_results": executed_results,
            "events": events,
            "reply": "暂时查不到任务状态，请稍后在画布查看，或点节点上的重试。",
            "reply_type": reply_type,
            "next_actions": [],
            "needs_reclock": False,
        }

    # 终态：取一次画布上下文，用节点标题对用户表达（不暴露内部 id）
    terminal = status in ("succeeded", "failed", "expired", "cancelled", "settlement_error")
    canvas_ctx = _fetch_canvas_context(user_id, canvas_id) if terminal and canvas_id else {}
    title = note.get("title") or _node_title(canvas_ctx, node_id)

    if status == "succeeded":
        reply = f"「{title}」生成完成，产物已写回画布。"
        next_actions = []
        events.append({"type": "canvas_changed", "tool": "task_complete", "data": result})

        downstream_results, downstream_labels, ds_reclock = _execute_downstream_submits(
            state, canvas_ctx, int(node_id) if node_id else None,
        )
        if downstream_results:
            executed_results.extend(downstream_results)
            needs_reclock = needs_reclock or ds_reclock
            joined = "、".join(downstream_labels[:4])
            if len(downstream_labels) > 4:
                joined += f" 等 {len(downstream_labels)} 项"
            reply += f"\n依赖已就绪，已自动提交：{joined}。我会继续跟进生成状态。"
        else:
            reply += " 下游节点尚不可用或仍在排队，我会继续监控。"

    elif status == "failed":
        reason = _humanize_task_error(result)
        reply = f"「{title}」生成失败：{reason}。可以调整 Prompt 后重试，或换模型再试。"
        next_actions = []

    elif status == "expired":
        reply = f"「{title}」排队超时，任务已过期，冻结的点数已自动退回。可以重新提交生成。"
        next_actions = []

    elif status == "cancelled":
        reply = f"「{title}」任务已取消，未发生扣费。"
        next_actions = []

    elif status == "settlement_error":
        reply = (
            f"「{title}」产物已写回画布，但点数结算异常；系统会自动重试结算，"
            "如发现点数异常请联系客服。"
        )
        next_actions = []

    return {
        "executed_results": executed_results,
        "events": events,
        "reply": reply,
        "reply_type": reply_type,
        "next_actions": next_actions,
        "needs_reclock": needs_reclock,
    }
