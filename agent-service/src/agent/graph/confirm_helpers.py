"""对话内确认：显式指令自动确认 / 文本「确认」「取消」续跑。"""

from __future__ import annotations

import re

EXPLICIT_EXEC = re.compile(
    r"生成|提交|做成|转换|图生视频|删除|移除|覆盖|重做|重跑",
    re.I,
)

_CONFIRM = re.compile(
    r"^(确认|确定|好的|好|是|是的|可以|行|执行|继续|同意|ok|yes|y)$",
    re.I,
)
_CANCEL = re.compile(r"^(取消|不要|算了|拒绝|no|n)$", re.I)


def should_auto_confirm(user_content: str, tool_name: str) -> bool:
    """用户已给出明确执行意图时，在对话内视为已确认，不再弹出按钮。"""
    content = (user_content or "").strip()
    if not content:
        return False
    if tool_name == "delete_nodes":
        return bool(re.search(r"删除|移除", content, re.I))
    if tool_name in (
        "submit_generation",
        "replace_output",
        "change_model",
        "extract_frames",
        "trim_clip",
        "upscale",
        "compose_final",
        "capture_3d_scene",
    ):
        return bool(EXPLICIT_EXEC.search(content))
    return False


def _cost_suffix(cost: int, chain: int) -> str:
    if cost <= 0 and chain <= 0:
        return ""
    if chain > 0:
        return f"（本次预估 {cost} 点；后续就绪节点将自动提交，整条链路合计约 {cost + chain} 点）"
    return f"（预估 {cost} 点）"


def build_inline_confirm_text(action: dict, *, accepted: bool, chain_cost: int = 0) -> str:
    params = action.get("params") or {}
    cost = int(params.get("estimated_cost") or params.get("estimatedCost") or 0)
    chain = int(chain_cost or params.get("chain_estimated_cost") or 0)
    summary = action.get("summary") or action.get("tool_name") or "操作"
    if accepted:
        return f"已确认：{summary}{_cost_suffix(cost, chain)}"
    return f"已取消：{summary}"


def build_dialog_confirm_prompt(action: dict, chain_cost: int = 0) -> str:
    params = action.get("params") or {}
    cost = int(params.get("estimated_cost") or params.get("estimatedCost") or 0)
    chain = int(chain_cost or params.get("chain_estimated_cost") or params.get("chainEstimatedCost") or 0)
    summary = action.get("summary") or action.get("tool_name") or "操作"
    if cost > 0 and chain > 0:
        cost_line = (
            f"本次预估 {cost} 点；确认后依赖就绪的下游节点将自动提交，"
            f"整条链路合计约 {cost + chain} 点。"
        )
    elif cost > 0:
        cost_line = f"预估 {cost} 点。"
    elif chain > 0:
        cost_line = f"确认后依赖就绪的下游节点将自动提交，预估约 {chain} 点。"
    else:
        cost_line = ""
    return (
        f"即将执行：{summary}。{cost_line}\n"
        "请在对话中回复「确认」继续，或「取消」放弃。"
    )


def parse_confirm_intent(content: str) -> str | None:
    text = (content or "").strip()
    if not text:
        return None
    if _CONFIRM.match(text):
        return "accept"
    if _CANCEL.match(text):
        return "cancel"
    return None
