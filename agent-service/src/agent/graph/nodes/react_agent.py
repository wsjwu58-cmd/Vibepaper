"""多轮 ReAct：按需 load_skill，观察后再 edit/exec。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from ...agent.persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS
from ...domain.turn_policy import (
    is_genuine_user_gap,
    is_process_narration,
    silence_process_reply,
)
from ...core.config import settings
from ...domain.llm_prompt import build_chat_messages
from ...domain.plan_models import PlanStep, StructuredPlan, extract_misplaced_actions, plan_to_dict
from ...domain.skill_catalog import skill_instructions_bundle
from ..state import AgentState

logger = logging.getLogger("agent.graph.react_agent")

DEFAULT_MAX_REACT_STEPS = 8

_ALLOWED_TOOLS = frozenset({
    "get_canvas_summary", "get_selected_nodes", "list_models", "search_assets",
    "load_skill", "check_task_status",
    "create_nodes", "connect_nodes", "layout_nodes", "update_node_config",
    "delete_nodes", "change_model", "replace_output",
    "submit_generation", "compose_final", "extract_frames", "trim_clip", "upscale",
})


def _sid(prefix: str = "step") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _tool_kind(tool: str) -> str:
    if tool == "load_skill":
        return "load_skill"
    if tool.startswith(("get_", "list_", "search_", "check_")):
        return "read"
    if tool in ("submit_generation", "compose_final", "extract_frames", "trim_clip", "upscale"):
        return "exec"
    return "edit"


def actions_to_plan(
    actions: list[dict[str, Any]],
    *,
    goal: str,
    reply: str,
    thinking: str,
    next_actions: list[str] | None = None,
    ask_user: bool = False,
    ask_question: str = "",
) -> StructuredPlan:
    steps: list[PlanStep] = []
    prev: str | None = None
    for item in actions:
        tool = str(item.get("tool") or item.get("tool_name") or "").strip()
        if not tool or tool not in _ALLOWED_TOOLS:
            continue
        sid = _sid(tool[:12])
        step = PlanStep(
            id=sid,
            kind=_tool_kind(tool),  # type: ignore[arg-type]
            title=str(item.get("summary") or tool),
            purpose=str(item.get("reasoning") or ""),
            depends_on=[prev] if prev else [],
            payload={"tool": tool, "params": dict(item.get("params") or {})},
        )
        steps.append(step)
        prev = sid
    return StructuredPlan(
        goal=goal or "创作任务",
        workflow="react",
        steps=steps,
        reply=reply or "",
        thinking=thinking or "",
        next_actions=list(next_actions or []),
        user_decision_required=ask_user,
        constraints={"ask_question": ask_question} if ask_question else {},
        completion_criteria=["本拍工具已执行或已结束"],
    )


def _rails_shortcut(state: AgentState) -> StructuredPlan | None:
    """画布已有链路时的合成/推进：不经 ReAct 瞎搭。"""
    content = state.get("user_content") or ""
    ctx = state.get("canvas_context") or {}
    intent = state.get("intent") or {}
    intent_name = str(intent.get("name") or "")

    from ...domain.creative_planner import compile_execution_plan
    from ...domain.pipeline import canvas_has_workflow, wants_direct_compose, wants_new_independent_create, wants_rebuild_workflow

    if not ctx:
        return None
    if wants_new_independent_create(content) or wants_rebuild_workflow(content):
        return None
    if intent_name in ("advance_pipeline", "regenerate_stale"):
        return compile_execution_plan(
            content,
            intent_name=intent_name,
            requested_skill=intent.get("requested_skill"),
            creative={"thinking": "铁路：推进/重跑"},
            canvas_context=ctx,
        )
    if canvas_has_workflow(ctx) and not wants_rebuild_workflow(content):
        if wants_direct_compose(content) or ("合成" in content and "短剧" not in content):
            return compile_execution_plan(
                content,
                intent_name="advance_pipeline",
                requested_skill=None,
                creative={"thinking": "铁路：直接合成"},
                canvas_context=ctx,
            )
    return None


def _fallback_narrow_actions(content: str, canvas: dict | None) -> list[dict[str, Any]]:
    """无 LLM 时的窄降级：单点媒体 / 图→视频，不搭短剧空壳。"""
    from ...agent.planner import plan as rule_plan

    actions = rule_plan(content, canvas or {}, [])
    # 拦截整包短剧脚手架
    creates = [a for a in actions if a.tool_name == "create_nodes"]
    total_nodes = sum(len((a.params or {}).get("nodes") or []) for a in creates)
    if total_nodes >= 6:
        return []
    return [
        {
            "tool": a.tool_name,
            "params": a.params,
            "summary": a.summary,
            "reasoning": a.reasoning,
        }
        for a in actions
    ]


def _last_observation_failures(observations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    fails: list[dict[str, Any]] = []
    for o in list(observations or [])[-6:]:
        if not isinstance(o, dict):
            continue
        if o.get("ok") is False:
            fails.append(o)
    return fails


def _call_react_llm(
    *,
    content: str,
    skill_instructions: str,
    canvas_context: dict[str, Any],
    selected_nodes: list[int],
    observations: list[dict[str, Any]],
    executed_results: list[dict[str, Any]] | None,
    recent_messages: list[dict[str, Any]] | None,
    project_memories: list[dict[str, Any]] | None,
    long_term_prefs: list[str] | None,
    loaded_keys: list[str],
    react_step: int,
    max_steps: int,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    import httpx

    fails = _last_observation_failures(observations)
    fail_hint = ""
    if fails:
        fail_hint = (
            "上一拍 Observation 有失败："
            + "; ".join(
                f"{f.get('tool')}→{str((f.get('data') or {}).get('error') or f.get('summary') or 'fail')[:80]}"
                for f in fails[-3:]
            )
            + "。本拍 Thought 必须分析原因并给出修正 Action，禁止 decision=finish。\n"
        )

    extra_rules = (
        "你运行在严格 ReAct 闭环：Thought → Action → Observation → Thought…\n"
        "每一拍只做「一小步」，不要一次吐完整长链路。\n"
        f"{fail_hint}"
        "—— 对用户开口的铁律 ——\n"
        "- 未完成任务时 reply 必须为空。过程独白只写 thinking，禁止「我先加载技能」「接下来创建节点」。\n"
        "- ask_user 仅当缺了无法默认的用户决策（主题/人物/二选一风格）且本拍 actions 为空；"
        "可按 Skill 默认继续时禁止提问、禁止停下来等确认。\n"
        "- finish 仅当目标已在画布落地（已 create/submit）或确认无需再动；"
        "禁止空 actions + 一段执行说明就结束。\n"
        "—— Thought（thinking 字段）——\n"
        "1. 先引用最新 Observation / 画布事实（有则必须点名工具结果或节点状态）；无观察则说明为何可直接行动。\n"
        "2. 判断目标是否已达成；未达成则拆出本拍唯一优先动作。\n"
        "3. 若 Observation 失败：分析原因，改参数/换工具/先 get_canvas_summary，禁止重复盲试同一错误。\n"
        "—— Action（actions 字段）——\n"
        "- 外部接地优先：缺画布事实 → get_canvas_summary / get_selected_nodes；缺规则 → load_skill。\n"
        "- 再 edit：create_nodes / connect_nodes / update_node_config / layout_nodes。\n"
        "- 再 exec：submit_generation / compose_final / extract_frames / trim_clip（仅依赖已就绪）。\n"
        "- 本拍 0–3 个工具；decision=act 表示执行后还要继续观察再想。\n"
        "- 用户已选定风格/方案后：必须 act + create_nodes，禁止口头承诺空 actions / 仅 load_skill 就 finish。\n"
        "- 禁止空模板壳；禁止编造分辨率/时长/模型名；禁止整段复制用户原话进 prompt。\n"
        "- 用户显式指令优先于 Skill 默认。\n"
        f"当前步={react_step}/{max_steps}\n"
        f"已加载 Skill 规则摘要=\n{(skill_instructions or PAPER_AGENT_INSTRUCTIONS)[:3500]}"
    )
    output_contract = (
        "输出严格 JSON（不要 Markdown）：\n"
        '{"thinking":"Thought：引用Observation→判断→下一步为何",'
        '"decision":"act|finish|ask_user","ask_question":"",'
        '"reply":"仅任务完成或真正提问时给用户；过程中必须为空",'
        '"next_actions":["短句1","短句2"],'
        '"actions":[{"tool":"","params":{},"summary":"","reasoning":""}]}\n'
        "thinking = Thought（内心独白，须接地 Observation/画布）；"
        "actions = Action；执行结果由系统写入 Observation 供下一拍。\n"
        "next_actions 只能是可点击短句字符串，禁止工具对象；禁止固定词表。"
    )
    messages = build_chat_messages(
        user_content=content,
        persona=AGENT_PERSONA,
        skill_instructions=skill_instructions or PAPER_AGENT_INSTRUCTIONS,
        extra_rules=extra_rules,
        output_contract=output_contract,
        include_tools=True,
        include_skills_catalog=True,
        recent_messages=recent_messages,
        project_memories=project_memories,
        long_term_prefs=long_term_prefs,
        observations=observations,
        executed_results=executed_results,
        canvas_context=canvas_context,
        selected_nodes=selected_nodes,
        loaded_skill_keys=loaded_keys,
        extra_context={
            "react_step": react_step,
            "max_react_steps": max_steps,
            "failed_observations": fails[-3:],
            "react_protocol": "Thought→Action→Observation",
        },
    )
    base = (base_url or "https://apihub.agnes-ai.com/v1").rstrip("/")
    if ("agnes-ai.com" in base or "deepseek.com" in base) and not base.endswith("/v1"):
        base = f"{base}/v1"
    resp = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"] or "{}"
    from ...domain.llm_json import parse_llm_json

    return parse_llm_json(raw, expect=dict)


def _looks_like_choice_continue(content: str) -> bool:
    text = (content or "").strip()
    if "选择：" in text or "请立刻按该选项" in text:
        return True
    return bool(re.match(r"^[A-Da-d1-4]\s*$", text))


def _looks_like_creative_bootstrap(content: str) -> bool:
    """用户明确要搭短剧/分镜/六格等创作链路（即使意图被标成 discussion）。"""
    text = content or ""
    from ...domain.workflow_orchestrator import (
        is_bootstrap_short_drama,
        is_workflow_orchestration_request,
    )

    if is_bootstrap_short_drama(text) or is_workflow_orchestration_request(text):
        return True
    return bool(re.search(
        r"(创建|做|生成|搭建|写).{0,16}(短剧|六格|漫画|海报|分镜|剧情|脚本)|"
        r"(短剧|六格|漫画|海报).{0,8}(创建|做|生成|搭建)",
        text,
        re.I,
    ))


def _reply_promises_canvas_work(reply: str) -> bool:
    return bool(re.search(
        r"落.*节点|创建.*节点|先落|项目简报|搭建|开始.*链路|写进画布|建.*分镜",
        reply or "",
    ))


def _structured_workflow_fallback(state: AgentState) -> StructuredPlan | None:
    """ReAct 空拍时：对明确工作流意图回退到创意编译，避免「本轮没有操作」。"""
    intent = state.get("intent") or {}
    name = str(intent.get("name") or "")
    wants = bool(intent.get("wants_execution"))
    content = state.get("user_content") or ""
    choice_continue = _looks_like_choice_continue(content)
    bootstrap = _looks_like_creative_bootstrap(content)
    if (
        not wants
        and name not in ("workflow_orchestration", "direct_canvas_action", "edit_existing")
        and not choice_continue
        and not bootstrap
    ):
        return None
    if name not in ("workflow_orchestration", "direct_canvas_action", "edit_existing", "unknown"):
        # 仍允许「…短剧」口语 / 选项续跑 / 创作引导句
        if (
            not choice_continue
            and not bootstrap
            and "短剧" not in content
            and "六格" not in content
            and "海报" not in content
            and "create_nodes" not in content
        ):
            return None
    try:
        from ...domain.creative_planner import build_structured_plan

        # 选项续跑 / 创作引导：强制执行意图，避免讨论态挡住编译
        intent_for_plan = dict(intent) if isinstance(intent, dict) else {}
        if choice_continue or bootstrap:
            intent_for_plan["wants_execution"] = True
            if intent_for_plan.get("name") in ("discussion", "unknown", "", None):
                intent_for_plan["name"] = "workflow_orchestration"

        plan = build_structured_plan(
            content,
            intent=intent_for_plan,
            skill_keys=list(state.get("selected_skill_keys") or []),
            canvas_context=state.get("canvas_context"),
            api_key=settings.llm_api_key or None,
            base_url=settings.normalized_llm_base_url(),
            model=settings.llm_model,
            recent_messages=list(state.get("recent_messages") or []),
            project_memories=list(state.get("project_memories") or []),
            long_term_prefs=list(state.get("long_term_prefs") or []),
            observations=list(state.get("observations") or []),
        )
        if plan and plan.steps:
            return plan
        # 编译拒绝（缺创意）时仍返回计划，便于上层用 reply 代替「没有操作」
        if plan and (plan.reply or plan.user_decision_required):
            return plan
    except Exception as exc:
        logger.warning("structured workflow fallback failed: %s", exc)
    return None


def react_agent_node(state: AgentState) -> dict:
    """ReAct 一拍：decide act/finish/ask_user，必要时产出本拍 tools。"""
    step = int(state.get("react_step") or 0) + 1
    max_steps = int(state.get("max_react_steps") or DEFAULT_MAX_REACT_STEPS)
    content = state.get("user_content") or ""
    ctx = state.get("canvas_context") or {}
    events: list[dict[str, Any]] = []

    # 铁路短路（首拍或 reconcile 进入时）
    if step <= 1:
        rails = _rails_shortcut(state)
        if rails and rails.steps:
            events.append({"type": "thinking", "content": rails.thinking or "铁路：复用画布推进"})
            for s in rails.steps:
                events.append({
                    "type": "plan_step",
                    "tool": (s.payload or {}).get("tool"),
                    "summary": s.title,
                    "reasoning": s.purpose,
                    "step_id": s.id,
                    "kind": s.kind,
                })
            return {
                "react_mode": True,
                "react_step": step,
                "max_react_steps": max_steps,
                "react_decision": "finish",
                "plan": plan_to_dict(rails),
                "reply": "",
                "next_actions": rails.next_actions or [],
                "validation_route": "execute",
                "needs_user_input": False,
                "terminal_status": "running",
                "events": events,
            }

    if step > max_steps:
        reply = (state.get("reply") or "") + f"\n已达本轮步数上限（{max_steps}），先停在这里；需要的话再说「继续」。"
        return {
            "react_mode": True,
            "react_step": step,
            "react_decision": "finish",
            "reply": reply.strip(),
            "validation_route": "finalize",
            "planned_actions": [],
            "executable_actions": [],
            "terminal_status": "completed",
            "events": [{"type": "react_cap", "step": step, "max": max_steps}],
        }

    data: dict[str, Any] = {}
    api_key = settings.llm_api_key or None
    if api_key:
        try:
            data = _call_react_llm(
                content=content,
                skill_instructions=state.get("skill_instructions") or "",
                canvas_context=ctx,
                selected_nodes=list(state.get("selected_nodes") or []),
                observations=list(state.get("observations") or []),
                executed_results=list(state.get("executed_results") or []),
                recent_messages=list(state.get("recent_messages") or []),
                project_memories=list(state.get("project_memories") or []),
                long_term_prefs=list(state.get("long_term_prefs") or []),
                loaded_keys=list(state.get("selected_skill_keys") or []),
                react_step=step,
                max_steps=max_steps,
                api_key=api_key,
                base_url=settings.normalized_llm_base_url(),
                model=settings.llm_model,
            )
        except Exception as exc:
            logger.warning("react llm failed: %s", exc)
            # JSON/网络失败：优先工作流编译，避免「没有操作」
            fb = _structured_workflow_fallback(state)
            if fb and fb.steps:
                events.append({
                    "type": "thinking",
                    "content": f"模型输出异常，改用工作流编译继续：{str(exc)[:60]}",
                })
                if fb.thinking:
                    events.append({"type": "thinking", "content": fb.thinking})
                for s in fb.steps:
                    events.append({
                        "type": "plan_step",
                        "tool": (s.payload or {}).get("tool"),
                        "summary": s.title,
                        "reasoning": s.purpose,
                        "step_id": s.id,
                        "kind": s.kind,
                    })
                return {
                    "react_mode": True,
                    "react_step": step,
                    "max_react_steps": max_steps,
                    "react_decision": "finish",
                    "plan": plan_to_dict(fb),
                    "reply": "",
                    "next_actions": fb.next_actions or [],
                    "validation_route": "execute",
                    "needs_user_input": False,
                    "terminal_status": "running",
                    "events": events,
                }
            data = {
                "thinking": f"模型输出解析失败：{str(exc)[:80]}",
                "decision": "act",
                "reply": "",
                "actions": _fallback_narrow_actions(content, ctx),
            }
    else:
        data = {
            "thinking": "无 LLM：窄规则降级",
            "decision": "act",
            "reply": "",
            "actions": _fallback_narrow_actions(content, ctx),
        }

    decision = str(data.get("decision") or "act").strip().lower()
    if decision not in ("act", "finish", "ask_user"):
        decision = "act"
    actions_raw = data.get("actions") or []
    if not isinstance(actions_raw, list):
        actions_raw = []
    next_actions, salvaged = extract_misplaced_actions(data.get("next_actions") or [])
    if salvaged:
        actions_raw = list(actions_raw) + salvaged

    def _tool_name(item: dict[str, Any]) -> str:
        return str(item.get("tool") or item.get("tool_name") or "").strip()

    thinking = str(data.get("thinking") or "")
    reply = str(data.get("reply") or "")
    ask_q = str(data.get("ask_question") or "")
    intent = state.get("intent") or {}
    wants = bool(intent.get("wants_execution")) if isinstance(intent, dict) else False
    keep_working = (
        wants
        or _looks_like_choice_continue(content)
        or _looks_like_creative_bootstrap(content)
        or _reply_promises_canvas_work(reply)
    )

    # 仅 load_skill/只读却 finish → 强制再拍，否则加载完就停、画布零改动
    prep_only = bool(actions_raw) and all(
        _tool_name(a) in ("load_skill", "get_canvas_summary", "get_selected_nodes", "list_models")
        for a in actions_raw
        if isinstance(a, dict)
    )
    if decision == "finish" and prep_only and keep_working:
        decision = "act"

    # Observation 失败时禁止 finish：强制继续 Thought→Action 纠错
    obs_fails = _last_observation_failures(list(state.get("observations") or []))
    if decision == "finish" and obs_fails and step < max_steps:
        decision = "act"
        if not actions_raw:
            actions_raw = [{
                "tool": "get_canvas_summary",
                "params": {},
                "summary": "失败后重读画布，再决定修正动作",
                "reasoning": "上一拍 Observation 失败，先接地再纠错",
            }]
        if not thinking:
            thinking = (
                "上一拍工具失败："
                + "; ".join(str(f.get("tool") or "") for f in obs_fails[-2:])
                + "。本拍先观察再修正，不结束。"
            )

    # 假提问：有主题/有步骤就继续干，禁止「我先加载技能可以吗」停下来
    if decision == "ask_user":
        genuine = is_genuine_user_gap(
            question=ask_q or reply,
            content=content,
            wants_execution=wants or keep_working,
            has_steps=bool(actions_raw),
            selected_nodes=list(state.get("selected_nodes") or []),
            canvas=ctx,
        )
        if not genuine:
            decision = "act"
            ask_q = ""
            if is_process_narration(reply):
                thinking = thinking or reply
            reply = ""

    # 执行中：过程话术只进 thinking，不进对话气泡
    if decision == "act":
        if reply and (is_process_narration(reply) or keep_working):
            thinking = thinking or reply
            reply = ""
        reply = ""

    # 无动作：能继续就编译/接地，禁止空 finish 对用户说话
    if decision == "act" and not actions_raw:
        if keep_working and step <= max_steps:
            decision = "act"
        else:
            decision = "finish"

    if thinking:
        events.append({"type": "thinking", "content": thinking})
    events.append({
        "type": "react_step",
        "step": step,
        "decision": decision,
        "action_count": len(actions_raw),
    })

    if decision == "ask_user":
        q = silence_process_reply(ask_q or reply, keep_if_genuine_ask=True) or (
            "还缺具体主题/人物/风格，补一句我就能继续搭。"
        )
        plan = actions_to_plan(
            [],
            goal="等待用户决策",
            reply=q,
            thinking=thinking,
            next_actions=next_actions,
            ask_user=True,
            ask_question=q,
        )
        return {
            "react_mode": True,
            "react_step": step,
            "max_react_steps": max_steps,
            "react_decision": "ask_user",
            "plan": plan_to_dict(plan),
            "reply": q,
            "next_actions": next_actions,
            "validation_route": "ask_user",
            "needs_user_input": True,
            "terminal_status": "waiting_user",
            "planned_actions": [],
            "executable_actions": [],
            "events": events,
        }

    plan = actions_to_plan(
        actions_raw,
        goal=str((intent.get("requested_skill") if isinstance(intent, dict) else None) or "创作任务"),
        reply=reply,
        thinking=thinking,
        next_actions=next_actions,
        ask_user=False,
    )
    for s in plan.steps:
        events.append({
            "type": "plan_step",
            "tool": (s.payload or {}).get("tool"),
            "summary": s.title,
            "reasoning": s.purpose,
            "step_id": s.id,
            "kind": s.kind,
        })

    if (decision in ("finish", "act")) and not plan.steps:
        fb = _structured_workflow_fallback(state)
        if fb and fb.steps:
            events.append({"type": "thinking", "content": fb.thinking or "空拍，继续按工作流执行"})
            for s in fb.steps:
                events.append({
                    "type": "plan_step",
                    "tool": (s.payload or {}).get("tool"),
                    "summary": s.title,
                    "reasoning": s.purpose,
                    "step_id": s.id,
                    "kind": s.kind,
                })
            # 编译出的是完整可执行图：本轮执行，不把过程话术发给用户
            return {
                "react_mode": True,
                "react_step": step,
                "max_react_steps": max_steps,
                "react_decision": "finish",
                "plan": plan_to_dict(fb),
                "reply": "",
                "next_actions": fb.next_actions or next_actions,
                "validation_route": "execute",
                "needs_user_input": False,
                "terminal_status": "running",
                "events": events,
            }
        if fb and not fb.steps and is_genuine_user_gap(
            question=fb.reply or ask_q,
            content=content,
            wants_execution=wants or keep_working,
            has_steps=False,
            selected_nodes=list(state.get("selected_nodes") or []),
            canvas=ctx,
        ):
            q = (fb.reply or "").strip() or "还缺具体主题/人物/风格，补一句我就能继续搭。"
            return {
                "react_mode": True,
                "react_step": step,
                "max_react_steps": max_steps,
                "react_decision": "ask_user",
                "plan": plan_to_dict(fb),
                "reply": q,
                "next_actions": fb.next_actions or next_actions,
                "validation_route": "ask_user",
                "needs_user_input": True,
                "terminal_status": "waiting_user",
                "events": events,
            }
        if keep_working and step < max_steps:
            # 还没做完：先读画布再进入下一拍，不结束对话
            plan = actions_to_plan(
                [{
                    "tool": "get_canvas_summary",
                    "params": {},
                    "summary": "继续任务前先核对画布",
                    "reasoning": "空拍但不允许中断，先接地再行动",
                }],
                goal="继续创作任务",
                reply="",
                thinking=thinking or "任务未完成，继续执行。",
            )
            events.append({
                "type": "plan_step",
                "tool": "get_canvas_summary",
                "summary": "继续任务前先核对画布",
            })
            return {
                "react_mode": True,
                "react_step": step,
                "max_react_steps": max_steps,
                "react_decision": "act",
                "plan": plan_to_dict(plan),
                "reply": "",
                "next_actions": next_actions,
                "validation_route": "execute",
                "needs_user_input": False,
                "terminal_status": "running",
                "events": events,
            }
        return {
            "react_mode": True,
            "react_step": step,
            "max_react_steps": max_steps,
            "react_decision": "finish",
            "plan": plan_to_dict(plan),
            "reply": silence_process_reply(reply),
            "next_actions": next_actions,
            "validation_route": "finalize",
            "planned_actions": [],
            "executable_actions": [],
            "terminal_status": "completed",
            "events": events,
        }

    # finish 但带最后一批 actions：执行完不再回环；act：执行完继续
    return {
        "react_mode": True,
        "react_step": step,
        "max_react_steps": max_steps,
        "react_decision": decision,
        "plan": plan_to_dict(plan),
        "reply": "" if decision == "act" else silence_process_reply(reply),
        "next_actions": next_actions,
        "validation_route": "execute" if plan.steps else "finalize",
        "needs_user_input": False,
        "terminal_status": "running",
        "events": events,
    }
