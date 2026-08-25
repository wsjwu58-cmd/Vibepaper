"""LLM 提示词组装：系统提示词 vs 用户提示词严格分层。

约定：
- system：人格、规则、工具清单、Skill 目录、已加载 Skill 规则（均可选调用）。
- user：本轮用户指令优先级最高，其后才是会话记忆、工具观察、画布事实。
工具与 Skill 列出即可，模型可按需调用，也可不调用。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 用户常回复「A」「B」「1」选择上轮 next_actions；选项往往只在 meta，不在正文。
_CHOICE_RE = re.compile(
    r"^(?:选(?:择)?|我(?:选|要)?|就|用)?\s*"
    r"([A-Da-d]|[1-4]|选项\s*[A-Da-d1-4])"
    r"(?:\s*[.。、:：)]?)?\s*$"
)


def tools_catalog_for_prompt(*, include_p2: bool = True) -> str:
    """从工具注册表白名单生成可调用工具说明。"""
    from ..tools.registry import TOOLS

    lines = [
        "可调用工具白名单（按需选用，也可不调用；禁止编造未列出的工具）：",
    ]
    for name, tool in TOOLS.items():
        if not include_p2 and getattr(tool, "category", "core") == "p2":
            continue
        risk = tool.risk_level
        cat = getattr(tool, "category", "core")
        lines.append(f"- {name} [{risk}/{cat}]：{tool.description}")
    return "\n".join(lines)


def _brief_json(obj: Any, limit: int = 2000) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    return text[:limit]


def _normalize_choice_token(raw: str) -> str | None:
    text = (raw or "").strip().upper().replace("选项", "").strip()
    if not text:
        return None
    if text in {"A", "B", "C", "D"}:
        return text
    if text in {"1", "2", "3", "4"}:
        return text
    return None


def _option_letter(text: str, index: int) -> str | None:
    """从「A. xxx」或列表下标提取选项字母/序号。"""
    s = (text or "").strip()
    m = re.match(r"^([A-Da-d])\s*[.．、:：)\]]\s*", s)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([1-4])\s*[.．、:：)\]]\s*", s)
    if m:
        return m.group(1)
    if 0 <= index < 4:
        return chr(ord("A") + index)
    return None


def last_offered_options(recent_messages: list[dict[str, Any]] | None) -> list[str]:
    """取最近一条助手消息里给出的可选项（优先 next_actions）。"""
    for msg in reversed(list(recent_messages or [])):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").lower() != "assistant":
            continue
        opts = msg.get("next_actions") or msg.get("nextActions") or []
        if isinstance(opts, list) and opts:
            return [str(x).strip() for x in opts if str(x).strip()][:8]
        # 正文里偶发内嵌 A/B/C
        content = str(msg.get("content") or "")
        embedded: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if re.match(r"^[A-Da-d1-4]\s*[.．、:：)\]]\s*\S", line):
                embedded.append(line)
        if embedded:
            return embedded[:8]
    return []


def resolve_option_choice(
    user_content: str,
    recent_messages: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None]:
    """若用户短回复 A/B/1…，对照上轮选项展开。

    Returns:
        (展示给模型的用户指令, 命中的选项原文或 None)
    """
    raw = (user_content or "").strip()
    if not raw:
        return raw, None
    m = _CHOICE_RE.match(raw)
    if not m:
        return raw, None
    token = _normalize_choice_token(m.group(1))
    if not token:
        return raw, None
    options = last_offered_options(recent_messages)
    if not options:
        return raw, None
    for idx, opt in enumerate(options):
        letter = _option_letter(opt, idx)
        if letter and letter == token:
            return f"选择：{opt}", opt
        # 用户打「A」而选项正文无前缀时，按顺序 A=第1条
        if token.isalpha() and letter == token:
            return f"选择：{opt}", opt
    # 纯数字且选项无编号：1→第1条
    if token.isdigit():
        i = int(token) - 1
        if 0 <= i < len(options):
            return f"选择：{options[i]}", options[i]
    return raw, None


def serialize_recent_message(
    *,
    role: str,
    content: str,
    msg_type: str = "text",
    meta: dict[str, Any] | None = None,
    content_limit: int = 800,
) -> dict[str, Any]:
    """供 context_builder 写入 recent_messages：正文 + 上轮选项芯片。"""
    meta = meta or {}
    item: dict[str, Any] = {
        "role": role,
        "type": msg_type,
        "content": (content or "")[:content_limit],
    }
    next_actions = meta.get("nextActions") or meta.get("next_actions") or []
    if isinstance(next_actions, list) and next_actions:
        item["next_actions"] = [str(x).strip() for x in next_actions if str(x).strip()][:8]
    return item


def _canvas_brief(canvas_context: dict[str, Any] | None) -> dict[str, Any]:
    ctx = canvas_context or {}
    keys = (
        "name", "nodeCount", "edgeCount", "nodeTypeCounts", "creativeTypeCounts",
        "keywords", "staleNodes", "pipelineHint", "inputChains", "targetContext",
    )
    out = {k: ctx.get(k) for k in keys if k in ctx}
    # 选中节点完整信息（prompt/params/上下游）供模型接地
    selected = ctx.get("selectedNodes")
    if isinstance(selected, list) and selected:
        briefs = []
        for n in selected[:6]:
            if not isinstance(n, dict):
                continue
            params = n.get("params") if isinstance(n.get("params"), dict) else {}
            briefs.append({
                "id": n.get("id"),
                "type": n.get("type"),
                "creativeType": n.get("creativeType"),
                "status": n.get("status") or n.get("execStatus"),
                "prompt": (n.get("prompt") or params.get("prompt") or "")[:400] or None,
                "title": params.get("title"),
                "modelRef": n.get("modelRef") or params.get("model"),
                "params": {
                    k: params.get(k)
                    for k in ("model", "aspect", "ratio", "duration", "resolution", "count")
                    if params.get(k) is not None
                } or None,
                "hasOutput": bool(n.get("output") or n.get("hasOutput") or params.get("lastOutputUrl")),
                "upstream": (n.get("upstream") or [])[:4],
                "downstream": (n.get("downstream") or [])[:4],
            })
        if briefs:
            out["selectedNodes"] = briefs
    return out


def _observations_brief(observations: list[dict[str, Any]] | None, limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for o in (observations or [])[-limit:]:
        data = o.get("data") if isinstance(o.get("data"), dict) else {}
        out.append({
            "tool": o.get("tool") or o.get("tool_name"),
            "ok": o.get("ok"),
            "summary": str(o.get("summary") or "")[:160],
            "error": (data or {}).get("error"),
            "skill_key": (data or {}).get("skill_key"),
            "result_keys": list((data or {}).keys())[:12] if data else [],
        })
    return out


def _executed_brief(executed_results: list[dict[str, Any]] | None, limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in (executed_results or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        if item.get("__replace_results__"):
            continue
        out.append({
            "tool": item.get("tool") or item.get("tool_name"),
            "ok": item.get("ok", item.get("success")),
            "summary": str(item.get("summary") or item.get("message") or "")[:160],
            "error": item.get("error"),
        })
    return out


def build_system_prompt(
    *,
    persona: str,
    skill_instructions: str = "",
    extra_rules: str = "",
    include_tools: bool = True,
    include_skills_catalog: bool = True,
    skills_catalog_limit: int = 12,
    output_contract: str = "",
) -> str:
    """组装 system 角色提示词（不含用户本轮原文）。"""
    from ..agent.persona import PAPER_AGENT_INSTRUCTIONS
    from .precedence import precedence_prompt_block
    from .skill_catalog import catalog_summary_for_prompt

    parts: list[str] = [
        persona.strip(),
        "",
        (skill_instructions or PAPER_AGENT_INSTRUCTIONS).strip(),
        "",
        "—— 提示词分层（强制）——",
        "1. 本消息为系统提示词：约束能力边界、工具/Skill 清单与输出格式。",
        "2. 用户消息中的「本轮用户指令」优先级最高：冲突时按用户方向解决，Skill/默认只补位。",
        "3. 工具与 Skill 均为可选：需要时调用，不需要则直接回答或结束本拍。",
        "4. 用户回复 A/B/C 或 1/2/3 时：必须对照会话里上轮助手的 next_actions/选项解析，"
        "禁止声称「上轮没给选项」；命中后按该选项推进，勿反复追问同一题。",
        "",
        precedence_prompt_block(),
    ]
    if include_tools:
        parts.extend(["", tools_catalog_for_prompt(include_p2=True)])
    if include_skills_catalog:
        parts.extend(["", catalog_summary_for_prompt(skills_catalog_limit)])
    if extra_rules.strip():
        parts.extend(["", extra_rules.strip()])
    if output_contract.strip():
        parts.extend(["", output_contract.strip()])
    return "\n".join(parts).strip()


def build_user_prompt(
    *,
    user_content: str,
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    executed_results: list[dict[str, Any]] | None = None,
    canvas_context: dict[str, Any] | None = None,
    selected_nodes: list[int] | None = None,
    loaded_skill_keys: list[str] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> str:
    """组装 user 角色提示词：用户指令优先，再附记忆与工具结果。"""
    recent = list(recent_messages or [])[-10:]
    resolved, matched = resolve_option_choice(user_content, recent)
    instruction = resolved.strip() or "（空）"
    if matched and resolved != (user_content or "").strip():
        instruction = (
            f"{instruction}\n"
            f"（用户原文「{(user_content or '').strip()}」= 选中上轮给出的该选项；"
            f"必须按此选项推进，禁止声称上轮未给选项。）"
        )

    sections: list[str] = [
        "【本轮用户指令｜最高优先级】",
        instruction,
        "",
        "以下为辅助上下文，仅在不违背用户指令时使用：",
    ]

    offered = last_offered_options(recent)
    if offered:
        sections.append("【上轮助手给出的可选项｜用户 A/B/C 或 1/2/3 须对照此处解析】")
        sections.append(_brief_json(offered, 1200))

    if recent:
        sections.append("【会话记忆｜最近对话】")
        sections.append(_brief_json(recent, 4000))

    prefs = list(long_term_prefs or [])[:6]
    if prefs:
        sections.append("【长期偏好】")
        sections.append(_brief_json(prefs, 600))

    mems = list(project_memories or [])[:8]
    if mems:
        sections.append("【项目记忆片段】")
        sections.append(_brief_json(mems, 1200))

    obs = _observations_brief(observations)
    if obs:
        sections.append("【Observation｜上一拍及近期工具结果｜下一拍 Thought 必须先引用再决策】")
        sections.append(_brief_json(obs, 2400))
        failed = [o for o in obs if o.get("ok") is False]
        if failed:
            sections.append("【失败 Observation｜须纠错：改参数/换工具/补读画布，禁止无视失败直接 finish】")
            sections.append(_brief_json(failed, 1200))

    exe = _executed_brief(executed_results)
    if exe:
        sections.append("【已执行工具返回摘要】")
        sections.append(_brief_json(exe, 1600))

    canvas = _canvas_brief(canvas_context)
    if canvas:
        sections.append("【画布摘要】")
        sections.append(_brief_json(canvas, 1600))

    if selected_nodes:
        sections.append(f"【选中节点 ID】{selected_nodes}")
        # 若画布摘要已带完整选中信息，提示模型以 selectedNodes 为准派生
        sel_detail = (canvas_context or {}).get("selectedNodes") if isinstance(canvas_context, dict) else None
        if isinstance(sel_detail, list) and sel_detail:
            sections.append("【选中节点完整信息｜派生新节点时须 connect input，禁止只在原节点硬提】")
            sections.append(_brief_json(sel_detail[:6], 2400))

    if loaded_skill_keys:
        sections.append(f"【已加载 Skill keys】{loaded_skill_keys}")

    if extra_context:
        sections.append("【其它上下文】")
        sections.append(_brief_json(extra_context, 1200))

    return "\n".join(sections).strip()


def build_chat_messages(
    *,
    user_content: str,
    persona: str,
    skill_instructions: str = "",
    extra_rules: str = "",
    output_contract: str = "",
    include_tools: bool = True,
    include_skills_catalog: bool = True,
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    executed_results: list[dict[str, Any]] | None = None,
    canvas_context: dict[str, Any] | None = None,
    selected_nodes: list[int] | None = None,
    loaded_skill_keys: list[str] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """返回 OpenAI 兼容 messages：system + user。"""
    system = build_system_prompt(
        persona=persona,
        skill_instructions=skill_instructions,
        extra_rules=extra_rules,
        include_tools=include_tools,
        include_skills_catalog=include_skills_catalog,
        output_contract=output_contract,
    )
    user = build_user_prompt(
        user_content=user_content,
        recent_messages=recent_messages,
        project_memories=project_memories,
        long_term_prefs=long_term_prefs,
        observations=observations,
        executed_results=executed_results,
        canvas_context=canvas_context,
        selected_nodes=selected_nodes,
        loaded_skill_keys=loaded_skill_keys,
        extra_context=extra_context,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
