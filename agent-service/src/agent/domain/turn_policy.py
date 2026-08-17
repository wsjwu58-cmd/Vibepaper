"""回合纪律：不到缺用户决策，不跟用户说话、不中断任务。

过程独白只进 thinking / 执行记录；对话气泡只用于：
- 任务完成后的结果；
- 真正缺条件时的一问。
"""

from __future__ import annotations

import re
from typing import Any

_PROCESS_NARRATION = re.compile(
    r"(我(先|将|会|来)|接下来|正在|让我|本拍|本轮|"
    r"先(加载|读取|看看|调用|确认一下)|开始(执行|搭建|工作)|"
    r"调用工具|执行过程|思考过程|load_skill|create_nodes|"
    r"请(稍等|稍候|稍等一下)|马上(开始|为你)|这就(开始|去))",
    re.I,
)

_FAKE_ASK = re.compile(
    r"(要(我|不要)?开始|可以吗|是否继续|要不要(我)?|"
    r"请确认后(我)?(开始|执行)|我先.{0,12}可以吗)",
    re.I,
)


def is_process_narration(text: str | None) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_PROCESS_NARRATION.search(t) or _FAKE_ASK.search(t))


def can_proceed_without_user(
    *,
    content: str,
    wants_execution: bool,
    has_steps: bool,
    selected_nodes: list | None = None,
    canvas: dict[str, Any] | None = None,
) -> bool:
    if has_steps:
        return True
    if selected_nodes:
        return True
    from .creative_planner import _theme_usable_as_creative
    from .prompt_builder import extract_theme

    if _theme_usable_as_creative(extract_theme(content)):
        return True
    ctx = canvas or {}
    if wants_execution and (ctx.get("nodeCount") or ctx.get("nodes")):
        return True
    return False


def is_genuine_user_gap(
    *,
    question: str | None,
    content: str,
    wants_execution: bool,
    has_steps: bool,
    selected_nodes: list | None = None,
    canvas: dict[str, Any] | None = None,
) -> bool:
    """只有「没有可执行步骤、且缺主题/决策」才打断用户。"""
    if has_steps:
        return False
    if can_proceed_without_user(
        content=content,
        wants_execution=wants_execution,
        has_steps=False,
        selected_nodes=selected_nodes,
        canvas=canvas,
    ):
        return False
    q = (question or "").strip()
    if q and is_process_narration(q):
        return False
    if q and _FAKE_ASK.search(q):
        return False
    # 无步骤且无法推进：需要用户补具体信息
    return True


def silence_process_reply(reply: str | None, *, keep_if_genuine_ask: bool = False) -> str:
    text = (reply or "").strip()
    if not text:
        return ""
    if keep_if_genuine_ask and not is_process_narration(text):
        return text
    if is_process_narration(text):
        return ""
    return text
