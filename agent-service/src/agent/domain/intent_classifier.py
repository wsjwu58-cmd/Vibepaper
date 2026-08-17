"""意图识别：全部由 LLM 完成，取消正则/关键词短路。

无 API Key 或 LLM 失败时返回低置信 unknown，交由后续节点兜底，
不再用正则假装高置信路由。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .llm_prompt import build_user_prompt
from .plan_models import IntentResult
from .skill_catalog import catalog_summary_for_prompt


def llm_classify_intent(
    content: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    canvas_context: dict[str, Any] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> IntentResult:
    import httpx

    system = (
        "你是 VibePaper 意图分类器。只做意图识别，不制定完整执行计划。\n"
        "用户消息中的「本轮用户指令」优先级最高；结合会话记忆与画布事实判断，禁止仅凭关键词猜测。\n"
        "输出严格 JSON（不要 Markdown）：\n"
        '{"name":"discussion|direct_canvas_action|workflow_orchestration|advance_pipeline|'
        'regenerate_stale|edit_existing|unknown",'
        '"confidence":0-1,"wants_execution":bool,"requested_skill":string|null,'
        '"target_description":string|null,"reasons":[string]}\n'
        "区分要点：\n"
        "1. 讨论 vs 执行（「六格漫画怎么排版」=discussion；「帮我生成六格漫画」=workflow_orchestration）；\n"
        "2. 新任务 / 修改已有 / 继续流程 / 重跑失败；\n"
        "3. 用户回复 A/B/C 或 1/2/3 且上轮助手给出了选项：=继续执行 "
        "（workflow_orchestration 或 edit_existing），wants_execution=true，绝不是 discussion；\n"
        "4. requested_skill 必须从目录选最贴合的 Skill key 或组合名"
        "（如 竖屏短剧 / 六格漫画 / film-poster / storyboard-shot-list）。"
        "用户没说出 Skill 名字也要选；不要默认竖屏短剧。"
        "仅当纯闲聊、问功能、完全无法对应任何 Skill 时才为 null。\n"
        f"{catalog_summary_for_prompt(12)}"
    )
    user = build_user_prompt(
        user_content=content,
        recent_messages=recent_messages,
        project_memories=project_memories,
        long_term_prefs=long_term_prefs,
        observations=observations,
        canvas_context=canvas_context,
    )

    base = (base_url or "https://apihub.agnes-ai.com/v1").rstrip("/")
    if ("agnes-ai.com" in base or "deepseek.com" in base) and not base.endswith("/v1"):
        base = f"{base}/v1"
    resp = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        },
        timeout=45,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"] or "{}"
    from .llm_json import parse_llm_json

    data = parse_llm_json(raw, expect=dict)
    return IntentResult.model_validate(data)


def _offline_fallback(content: str) -> IntentResult:
    """无 LLM 时的保守兜底：闲聊走讨论；其余交后续节点。"""
    text = (content or "").strip()
    if not text:
        return IntentResult(
            name="discussion",
            confidence=1.0,
            wants_execution=False,
            reasons=["空输入"],
        )
    if is_chitchat(text):
        return IntentResult(
            name="discussion",
            confidence=0.95,
            wants_execution=False,
            reasons=["闲聊/问候兜底"],
        )
    return IntentResult(
        name="unknown",
        confidence=0.2,
        wants_execution=True,
        reasons=["无 LLM，跳过正则意图，交由后续节点处理"],
    )


_CHITCHAT = re.compile(
    r"^(你好|您好|嗨|哈喽|在吗|早上好|下午好|晚上好|hello|hi|hey)"
    r"[\s!！。.?？~～❤️😊]*$",
    re.I,
)


def is_chitchat(content: str) -> bool:
    """纯问候/闲聊，应走讨论回复，禁止静默或写画布。"""
    return bool(_CHITCHAT.match((content or "").strip()))


def classify_intent_hybrid(
    content: str,
    *,
    api_key: str | None = None,
    base_url: str = "",
    model: str = "",
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    canvas_context: dict[str, Any] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> IntentResult:
    """LLM 意图识别入口（保留 hybrid 名称以兼容调用方）。

    已取消确定性正则短路；仅在无 key / 调用失败时走离线兜底。
    纯闲聊在调用 LLM 前短路，避免空回复。
    """
    if is_chitchat(content):
        return IntentResult(
            name="discussion",
            confidence=1.0,
            wants_execution=False,
            reasons=["闲聊/问候"],
        )
    if api_key:
        try:
            return llm_classify_intent(
                content,
                api_key=api_key,
                base_url=base_url,
                model=model,
                recent_messages=recent_messages,
                project_memories=project_memories,
                long_term_prefs=long_term_prefs,
                canvas_context=canvas_context,
                observations=observations,
            )
        except Exception as exc:
            fb = _offline_fallback(content)
            fb.reasons = list(fb.reasons or []) + [f"LLM 意图失败：{str(exc)[:80]}"]
            return fb
    return _offline_fallback(content)


def deterministic_intent_match(text: str) -> IntentResult | None:
    """已废弃：正则意图识别已移除，始终返回 None。

    保留符号以免旧测试/脚本硬崩；请改用 classify_intent_hybrid / llm_classify_intent。
    """
    _ = text
    return None


def route_intent_name(intent: IntentResult) -> str:
    name = intent.name
    if name == "discussion" or (not intent.wants_execution and name in ("unknown", "discussion")):
        return "answer_discussion"
    if name == "advance_pipeline":
        return "reconcile_canvas"
    if name == "regenerate_stale":
        return "plan_recovery"
    if name == "direct_canvas_action":
        return "acquire_context"
    if name in ("workflow_orchestration", "edit_existing"):
        return "select_skill"
    if name == "unknown" and intent.wants_execution:
        return "select_skill"
    return "fallback"
