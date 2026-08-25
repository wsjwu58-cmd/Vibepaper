"""Creative Planner（LLM 内容）+ Execution Compiler（规则落工具步骤）。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .plan_models import PlanStep, StructuredPlan
from .prompt_builder import build_node_prompt, extract_theme, is_verbatim_user_dump
from .skill_catalog import (
    SkillDef,
    compile_profile_for,
    get_skill,
    primary_skill_key,
    resolve_route_keys,
    skill_instructions_bundle,
    trim_skeleton,
)
from .workflow_rails import IMAGE_PREF_MODEL, backfill_video_node_params


def _sid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def infer_trim_from_user(content: str) -> dict[str, Any]:
    """从用户指令推断骨架裁剪（规则，不靠 Skill 自己改）。"""
    skip: list[str] = []
    stop_after: str | None = None
    start_from: str | None = None
    if re.search(r"跳过角色|不要角色卡|无需角色", content):
        skip.extend(["角色", "一致性规范"])
    if re.search(r"只要剧本|只要脚本|不要分镜|不要生成素材|只(建|做)文本", content):
        stop_after = "剧本"
    if re.search(r"已有剧本|从分镜开始|直接分镜", content):
        start_from = "分镜"
    if re.search(r"不生成素材|不提交生成|只搭(节点|结构)", content):
        skip.append("__no_exec__")
    return {"skip_labels": skip, "stop_after": stop_after, "start_from": start_from}


def creative_plan_llm(
    *,
    content: str,
    intent: dict[str, Any],
    skill_instructions: str,
    canvas_context: dict[str, Any] | None,
    skeleton: list[str],
    api_key: str,
    base_url: str,
    model: str,
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """LLM 只产出创意结构与各步内容意图，不发明工具参数。"""
    import httpx

    from ..agent.persona import AGENT_PERSONA
    from .llm_prompt import build_chat_messages

    extra_rules = (
        "你是视频创作任务规划器（Creative Planner）。\n"
        "规则：\n"
        "- 用户显式指令优先于工作流默认值；Skill 只补充用户未指定的部分。\n"
        "- 必须按已选 Skill 的骨架编排节点，禁止无视 Skill 一律搭竖屏短剧。\n"
        "- 禁止把用户原话/整段指令复制进 script_prompt、character_prompt、"
        "storyboard_prompt、keyframe_prompt、clip_prompt；每个字段必须是该节点自己的生成指令。\n"
        "- 总脚本写剧情结构与对白；分镜写镜号/景别/动作；首帧写静帧构图；视频只写运镜与动态。\n"
        "- 不要为长脚本直接创建单个视频节点，要拆成镜头。\n"
        "- 缺少真实节点 ID 时标注 needs_lookup=true，不得编造 ID。\n"
        "- 只有真正缺少用户决策时才 set ask_user=true。\n"
        "- 不要把等待异步生成写成轮询。\n"
        f"骨架步骤={skeleton}\n"
        f"意图={json.dumps(intent, ensure_ascii=False)}"
    )
    output_contract = (
        "输出严格 JSON：\n"
        '{"goal":"","thinking":"","reply":"","ask_user":false,"ask_question":"",'
        '"selected_skill":"skill-key或组合名",'
        '"shots":[{"index":1,"title":"","keyframe_prompt":"","clip_prompt":""}],'
        '"script_prompt":"","character_prompt":"","storyboard_prompt":"",'
        '"completion_criteria":["..."],"next_actions":["短句1","短句2"],'
        '"skip_steps":[],"stop_after":null,"start_from":null}\n'
        "selected_skill 必须从目录选最贴合项；用户没点名 Skill 也要选，"
        "不要默认竖屏短剧，除非用户确实要短剧。\n"
        "注意：next_actions 只能是字符串短句，禁止放动作对象；须按当前上下文临场生成。"
    )
    messages = build_chat_messages(
        user_content=content,
        persona=AGENT_PERSONA,
        skill_instructions=skill_instructions,
        extra_rules=extra_rules,
        output_contract=output_contract,
        include_tools=True,
        include_skills_catalog=True,
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
            "messages": messages,
            "temperature": 0.35,
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"] or "{}"
    from .llm_json import parse_llm_json

    return parse_llm_json(raw, expect=dict)


def _theme_usable_as_creative(theme: str) -> bool:
    """主题是否具体到可当创意方向（排除纯流程指令）。"""
    t = (theme or "").strip()
    if len(t) < 4:
        return False
    if re.fullmatch(
        r"(直接)?合成|推进(下一阶段|下一步)?|继续|重跑|只要剧本|搭建(短剧)?|"
        r"(做|生成|搭建|创建)?(一个)?(30秒)?(竖屏)?短剧(链路|工作流)?|"
        r"按照工作流.*",
        t,
    ):
        return False
    # 去掉通用流程词后仍须留下主体
    stripped = re.sub(
        r"(30\s*秒|竖屏)?短剧|三个?镜头|\d+\s*镜|分镜|工作流|链路|搭建|生成|创建|"
        r"做一?[个条部]?|帮我|请|按照|流程",
        "",
        t,
        flags=re.I,
    )
    stripped = re.sub(r"[\d\s，,。；;、的]+", "", stripped).strip()
    return len(stripped) >= 2


def _blank_or_dump(value: Any, user_content: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return is_verbatim_user_dump(text, user_content)


def _expand_role_prompts(
    creative: dict[str, Any],
    content: str,
    theme: str,
) -> dict[str, Any]:
    """缺字段或原样粘贴用户指令时，按角色重写；主题只作题材。"""
    out = dict(creative or {})
    if not _theme_usable_as_creative(theme) and not _has_llm_creative_payload(out):
        return out
    direction = (theme or extract_theme(content) or "").strip()
    if not direction:
        return out
    out.setdefault("goal", direction)
    if _blank_or_dump(out.get("script_prompt"), content):
        out["script_prompt"] = build_node_prompt(role="script", user_theme=content, goal=direction)
    if _blank_or_dump(out.get("character_prompt"), content):
        out["character_prompt"] = build_node_prompt(role="character", user_theme=content, goal=direction)
    if _blank_or_dump(out.get("storyboard_prompt"), content):
        out["storyboard_prompt"] = build_node_prompt(role="shot", user_theme=content, goal=direction)
    if _blank_or_dump(out.get("compose_prompt"), content):
        out["compose_prompt"] = build_node_prompt(role="composite", user_theme=content, goal=direction)

    shots = [s for s in (out.get("shots") or []) if isinstance(s, dict)]
    rewritten: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        item = dict(shot)
        idx = int(item.get("index") or i + 1)
        if _blank_or_dump(item.get("keyframe_prompt"), content):
            item["keyframe_prompt"] = build_node_prompt(
                role="keyframe", user_theme=content, shot_index=idx, shot_count=max(len(shots), 1),
                goal=direction,
            )
        if _blank_or_dump(item.get("clip_prompt"), content):
            item["clip_prompt"] = build_node_prompt(
                role="clip", user_theme=content, shot_index=idx, shot_count=max(len(shots), 1),
                goal=direction,
            )
        rewritten.append(item)
    if rewritten:
        out["shots"] = rewritten
    if not str(out.get("thinking") or "").strip():
        out["thinking"] = f"按主题「{direction[:40]}」为各节点写角色化生成指令，不粘贴用户原话。"
    if not str(out.get("reply") or "").strip():
        out["reply"] = f"按「{direction[:40]}」开始按所选 Skill 搭建节点。"
    return out


def _has_llm_creative_payload(creative: dict[str, Any]) -> bool:
    """是否具备 LLM/用户提供的实质创意内容（禁止空模板壳兜底）。"""
    if str(creative.get("script_prompt") or "").strip():
        return True
    if str(creative.get("storyboard_prompt") or "").strip():
        return True
    if str(creative.get("character_prompt") or "").strip():
        return True
    for shot in creative.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        if str(shot.get("keyframe_prompt") or "").strip() or str(shot.get("clip_prompt") or "").strip():
            return True
    # from_llm alone 不够：空壳 LLM 结果仍须拒绝
    return False


def _refuse_empty_scaffold(content: str, creative: dict[str, Any]) -> StructuredPlan:
    theme = extract_theme(content) or "短剧"
    return StructuredPlan(
        goal=str(creative.get("goal") or theme),
        workflow="vertical-short-drama",
        steps=[],
        thinking=str(creative.get("thinking") or "空模板脚手架已下线，缺少 LLM 创意内容，不落空壳节点。"),
        reply=(
            "空模板脚手架已关闭：不会再创建「请直接写出总脚本…」这类占位节点。\n"
            "请用一句话写清人物、冲突与风格（例如「吕布骑赤兔在虎牢关大战三英」），"
            "我会按你的内容规划并调用工具生成。"
        ),
        next_actions=list(creative.get("next_actions") or []),
        user_decision_required=True,
        constraints={"ask_question": "请补充具体剧情/人物/风格后再搭建。"},
        completion_criteria=[],
    )


def _compile_short_drama(
    content: str,
    creative: dict[str, Any],
    *,
    no_exec: bool,
) -> StructuredPlan:
    """把 LLM 创意编译为短剧工具步骤；无创意内容时拒绝空模板脚手架。"""
    if not _has_llm_creative_payload(creative):
        return _refuse_empty_scaffold(content, creative)

    theme = extract_theme(content) or str(creative.get("goal") or "短剧")
    shots = [s for s in (creative.get("shots") or []) if isinstance(s, dict)]
    # 只保留带画面/动态描述的镜头；禁止 invent 空镜头再灌模板
    rich_shots = [
        s for s in shots
        if str(s.get("keyframe_prompt") or "").strip() or str(s.get("clip_prompt") or "").strip()
    ]
    script_prompt = str(creative.get("script_prompt") or "").strip()
    character_prompt = str(creative.get("character_prompt") or "").strip()
    storyboard_prompt = str(creative.get("storyboard_prompt") or "").strip()

    if not script_prompt and not rich_shots and not storyboard_prompt:
        return _refuse_empty_scaffold(content, creative)

    if _blank_or_dump(script_prompt, content):
        script_prompt = build_node_prompt(role="script", user_theme=content, goal=theme)
    if _blank_or_dump(storyboard_prompt, content):
        storyboard_prompt = build_node_prompt(role="shot", user_theme=content, goal=theme, shot_count=max(len(rich_shots) or 1, 1))
    if _blank_or_dump(character_prompt, content):
        character_prompt = build_node_prompt(role="character", user_theme=content, goal=theme)

    shots = rich_shots or shots
    if not shots:
        from .workflow_orchestrator import _extract_shot_count
        n = _extract_shot_count(content)
        shots = [
            {
                "index": i + 1,
                "title": f"镜头{i + 1}",
                "keyframe_prompt": build_node_prompt(
                    role="keyframe", user_theme=content, shot_index=i + 1, shot_count=n, goal=theme,
                ),
                "clip_prompt": build_node_prompt(
                    role="clip", user_theme=content, shot_index=i + 1, shot_count=n, goal=theme,
                ),
            }
            for i in range(n)
        ]
    shot_count = max(1, min(len(shots), 8))

    skip_char = any("角色" in s for s in (creative.get("skip_steps") or []))
    steps: list[PlanStep] = []

    s_read = _sid("read")
    steps.append(PlanStep(
        id=s_read, kind="read", title="读取画布现状",
        purpose="确认真实节点，避免编造",
        payload={"tool": "get_canvas_summary", "params": {}},
    ))

    # 文本底座 —— prompt 仅来自 LLM/用户主题
    base_nodes = [{
        "type": "text", "creativeType": "script", "x": 120, "y": 120,
        "params": {"prompt": script_prompt, "title": "总脚本"}, "prompt": script_prompt,
    }]
    shot_idx = 1
    if not skip_char:
        base_nodes.append({
            "type": "text", "creativeType": "character", "x": 120, "y": 200,
            "params": {"prompt": character_prompt, "title": "角色卡"}, "prompt": character_prompt,
        })
        shot_idx = 2
    base_nodes.append({
        "type": "text", "creativeType": "shot", "x": 120, "y": 280,
        "params": {"prompt": storyboard_prompt, "title": "分镜清单"}, "prompt": storyboard_prompt,
    })

    s_base = _sid("edit-base")
    steps.append(PlanStep(
        id=s_base, kind="edit", title="创建文本底座节点",
        purpose="总脚本/角色卡/分镜按产物边界拆分（内容来自创意规划）",
        depends_on=[s_read],
        payload={"tool": "create_nodes", "params": {"nodes": base_nodes}},
        idempotency_key=f"create-base:{theme[:40]}",
    ))

    edges_base = [{
        "sourceNodeId": "$created[0]",
        "targetNodeId": f"$created[{shot_idx}]",
        "dependencyType": "input",
    }]
    if not skip_char:
        edges_base.extend([
            {"sourceNodeId": "$created[0]", "targetNodeId": "$created[1]", "dependencyType": "input"},
            {"sourceNodeId": "$created[1]", "targetNodeId": f"$created[{shot_idx}]", "dependencyType": "input"},
        ])
    s_conn_base = _sid("edit-conn-base")
    steps.append(PlanStep(
        id=s_conn_base, kind="edit", title="文本底座连线",
        purpose="脚本/角色喂给分镜",
        depends_on=[s_base],
        payload={"tool": "connect_nodes", "params": {"edges": edges_base}},
    ))

    # 若只要剧本
    if creative.get("stop_after") and "剧本" in str(creative.get("stop_after")):
        if not no_exec:
            steps.append(PlanStep(
                id=_sid("exec-script"), kind="exec", title="提交总脚本",
                purpose="只生成剧本层",
                depends_on=[s_conn_base],
                payload={
                    "tool": "submit_generation",
                    "params": {
                        "node_id": "$created[0]",
                        "model_type": "text",
                        "model_params": {"prompt": script_prompt, "count": 1},
                        "estimated_cost": 5,
                    },
                },
            ))
        return StructuredPlan(
            goal=str(creative.get("goal") or f"短剧文本：{theme}"),
            workflow="vertical-short-drama",
            steps=steps,
            completion_criteria=creative.get("completion_criteria") or ["总脚本节点已创建"],
            reply=str(creative.get("reply") or "已按你的要求只搭建剧本层。"),
            thinking=str(creative.get("thinking") or ""),
            next_actions=list(creative.get("next_actions") or []),
            user_decision_required=bool(creative.get("ask_user")),
        )

    # 首帧 + 视频：只用 LLM 给出的镜级 prompt
    image_nodes = []
    for i, shot in enumerate(shots[:shot_count]):
        kp = str(shot.get("keyframe_prompt") or "").strip()
        if _blank_or_dump(kp, content):
            kp = build_node_prompt(
                role="keyframe", user_theme=content, shot_index=i + 1, shot_count=shot_count, goal=theme,
            )
        image_nodes.append({
            "type": "image", "creativeType": "keyframe",
            "x": 380, "y": 80 + i * 140,
            "params": {"prompt": kp, "title": shot.get("title") or f"镜头{i + 1}首帧", "model": IMAGE_PREF_MODEL},
            "prompt": kp,
        })
    s_kf = _sid("edit-kf")
    steps.append(PlanStep(
        id=s_kf, kind="edit", title=f"创建 {shot_count} 个首帧",
        purpose="逐镜视觉锚点（prompt 来自创意规划）",
        depends_on=[s_conn_base],
        payload={"tool": "create_nodes", "params": {"nodes": image_nodes}},
    ))

    kf_base = shot_idx + 1
    kf_edges_steps = []
    for i in range(shot_count):
        edges = [{
            "sourceNodeId": f"$created[{shot_idx}]",
            "targetNodeId": f"$created[{kf_base + i}]",
            "dependencyType": "input",
        }]
        if not skip_char:
            edges.append({
                "sourceNodeId": "$created[1]",
                "targetNodeId": f"$created[{kf_base + i}]",
                "dependencyType": "input",
            })
        sid = _sid(f"conn-kf-{i}")
        kf_edges_steps.append(sid)
        steps.append(PlanStep(
            id=sid, kind="edit", title=f"分镜→镜头{i + 1}首帧",
            purpose="首帧依赖分镜",
            depends_on=[s_kf],
            payload={"tool": "connect_nodes", "params": {"edges": edges}},
        ))

    video_nodes = []
    for i, shot in enumerate(shots[:shot_count]):
        cp = str(shot.get("clip_prompt") or "").strip()
        if _blank_or_dump(cp, content):
            cp = build_node_prompt(
                role="clip", user_theme=content, shot_index=i + 1, shot_count=shot_count, goal=theme,
            )
        params = {"prompt": cp, "title": f"镜头{i + 1}视频"}
        params.update(backfill_video_node_params(params, user_content=content))
        video_nodes.append({
            "type": "video", "creativeType": "clip",
            "x": 680, "y": 80 + i * 140,
            "params": params, "prompt": cp,
        })
    base_vid = kf_base + shot_count
    s_vid = _sid("edit-vid")
    dep_for_vid = kf_edges_steps or [s_kf]
    steps.append(PlanStep(
        id=s_vid, kind="edit", title=f"创建 {shot_count} 个视频节点",
        purpose="逐镜动态（prompt 来自创意规划）",
        depends_on=dep_for_vid,
        payload={"tool": "create_nodes", "params": {"nodes": video_nodes}},
    ))
    for i in range(shot_count):
        steps.append(PlanStep(
            id=_sid(f"conn-vid-{i}"), kind="edit", title=f"首帧→镜头{i + 1}视频",
            purpose="首帧喂视频",
            depends_on=[s_vid],
            payload={"tool": "connect_nodes", "params": {"edges": [{
                "sourceNodeId": f"$created[{kf_base + i}]",
                "targetNodeId": f"$created[{base_vid + i}]",
                "dependencyType": "input",
            }]}},
        ))

    compose_prompt = str(creative.get("compose_prompt") or "").strip()
    if _blank_or_dump(compose_prompt, content):
        compose_prompt = build_node_prompt(
            role="composite", user_theme=content, shot_count=shot_count, goal=theme,
        )
    compose_idx = base_vid + shot_count
    s_comp = _sid("edit-compose")
    steps.append(PlanStep(
        id=s_comp, kind="edit", title="创建成片节点",
        purpose="拼接各镜",
        depends_on=[s_vid],
        payload={"tool": "create_nodes", "params": {"nodes": [{
            "type": "compose", "creativeType": "composite",
            "x": 980, "y": 200,
            "params": {"prompt": compose_prompt, "title": "成片"}, "prompt": compose_prompt,
        }]}},
    ))
    steps.append(PlanStep(
        id=_sid("conn-compose"), kind="edit", title="各镜→成片",
        purpose="成片吃齐所有 clip",
        depends_on=[s_comp],
        payload={"tool": "connect_nodes", "params": {"edges": [
            {
                "sourceNodeId": f"$created[{base_vid + i}]",
                "targetNodeId": f"$created[{compose_idx}]",
                "dependencyType": "input",
            }
            for i in range(shot_count)
        ]}},
    ))
    s_layout = _sid("layout")
    steps.append(PlanStep(
        id=s_layout, kind="edit", title="整理布局",
        purpose="依赖图可视化",
        depends_on=[s_comp],
        payload={"tool": "layout_nodes", "params": {"layout": "auto"}},
    ))

    if not no_exec:
        from .dependency_scheduler import DEFAULT_COST
        steps.append(PlanStep(
            id=_sid("exec-root"), kind="exec", title="提交总脚本（链起点）",
            purpose="只提交无上游依赖的起点；下游等 ready 后自动推进",
            depends_on=[s_layout],
            payload={
                "tool": "submit_generation",
                "params": {
                    "node_id": "$created[0]",
                    "model_type": "text",
                    "model_params": {"prompt": script_prompt, "count": 1},
                    "estimated_cost": DEFAULT_COST["text"],
                    "chain_estimated_cost": DEFAULT_COST["text"] + DEFAULT_COST["image"] * shot_count
                    + DEFAULT_COST["video"] * shot_count + DEFAULT_COST["compose"],
                },
            },
        ))

    return StructuredPlan(
        goal=str(creative.get("goal") or f"竖屏短剧：{theme}"),
        workflow="vertical-short-drama",
        steps=steps,
        assumptions=list(creative.get("assumptions") or []),
        completion_criteria=list(creative.get("completion_criteria") or [
            "链路节点与依赖已搭建",
            "总脚本已提交或用户选择仅搭结构",
        ]),
        reply=str(creative.get("reply") or (
            f"已按你的创意搭建 {shot_count} 镜链路，并提交总脚本生成。"
        )),
        thinking=str(creative.get("thinking") or "结构由 Skill 骨架，内容来自创意规划。"),
        next_actions=list(creative.get("next_actions") or []),
        user_decision_required=bool(creative.get("ask_user")),
        constraints={"ask_question": creative.get("ask_question") or ""},
    )


def _placement_beside_selection(
    selected: list[int],
    canvas: dict[str, Any] | None,
    *,
    default_x: float = 240,
    default_y: float = 180,
) -> tuple[float, float]:
    if not selected or not canvas:
        return default_x, default_y
    nodes = {
        int(n["id"]): n
        for n in (canvas.get("selectedNodes") or canvas.get("nodes") or [])
        if n.get("id") is not None
    }
    xs, ys = [], []
    for sid in selected:
        n = nodes.get(int(sid))
        if not n:
            continue
        xs.append(float(n.get("x") or default_x))
        ys.append(float(n.get("y") or default_y))
    if not xs:
        return default_x, default_y
    return max(xs) + 300, sum(ys) / len(ys)


def _selected_connect_ids(
    selected: list[int],
    canvas: dict[str, Any] | None,
    *,
    prefer_dual_images: bool = False,
) -> list[int]:
    """多选连线顺序：双图首尾帧时图优先，其余文本随后。"""
    ids = [int(s) for s in selected[:4]]
    if not prefer_dual_images or not canvas:
        return ids
    nodes = {
        int(n["id"]): n
        for n in (canvas.get("selectedNodes") or canvas.get("nodes") or [])
        if n.get("id") is not None
    }
    image_ids = [
        int(sid) for sid in selected
        if str((nodes.get(int(sid)) or {}).get("type") or "") == "image"
    ]
    other_ids = [int(sid) for sid in selected if int(sid) not in image_ids]
    if len(image_ids) >= 2:
        return image_ids[:2] + other_ids[:2]
    if image_ids:
        return image_ids + other_ids
    return ids


def _steps_connect_selected(
    *,
    selected: list[int],
    target_created_idx: int,
    depends_on: list[str],
    canvas: dict[str, Any] | None = None,
    prefer_dual_images: bool = False,
) -> list[PlanStep]:
    if not selected:
        return []
    connect_ids = _selected_connect_ids(
        selected, canvas, prefer_dual_images=prefer_dual_images,
    )
    target = f"$created[{int(target_created_idx)}]"
    edges = [
        {
            "sourceNodeId": int(sid),
            "targetNodeId": target,
            "dependencyType": "input",
        }
        for sid in connect_ids
    ]
    reason = "选中参考经 input 喂给 Skill 产物节点"
    if prefer_dual_images and len(connect_ids) >= 2:
        reason += "；多图按顺序作首帧/尾帧"
    return [
        PlanStep(
            id=_sid("conn-sel"),
            kind="edit",
            title="连接选中参考 → Skill 产物",
            purpose=reason,
            depends_on=list(depends_on),
            payload={"tool": "connect_nodes", "params": {"edges": edges}},
        ),
    ]


def _visual_image_prompts(
    content: str,
    skill: SkillDef,
    creative: dict[str, Any],
    theme: str,
    count: int,
) -> list[str]:
    prompts: list[str] = []
    shots = [s for s in (creative.get("shots") or []) if isinstance(s, dict)]
    for i in range(count):
        raw = ""
        if i == 0:
            raw = str(creative.get("script_prompt") or creative.get("keyframe_prompt") or "").strip()
        if not raw and i < len(shots):
            raw = str(shots[i].get("keyframe_prompt") or "").strip()
        if _blank_or_dump(raw, content):
            raw = build_node_prompt(
                role="image", user_theme=content, shot_index=i + 1, shot_count=count, goal=theme,
            )
            if raw:
                raw = f"【{skill.name}】{raw}"
                if count > 1:
                    raw = f"{raw}（第 {i + 1}/{count} 幅，叙事连贯）"
        prompts.append(raw or f"{skill.name}：{theme}")
    return prompts


def _compile_simple_visual(
    content: str,
    skill: SkillDef,
    creative: dict[str, Any],
    *,
    selected_nodes: list[int] | None = None,
    canvas_context: dict[str, Any] | None = None,
) -> StructuredPlan:
    """视觉 Skill playbook：落图节点；有选中则连参考再提交。三联图落 3 张。"""
    theme = extract_theme(content)
    selected = [int(x) for x in (selected_nodes or [])]
    count = 3 if skill.key == "cinematic-triptych" else 1
    prompts = _visual_image_prompts(content, skill, creative, theme, count)
    ratio = (skill.default_constraints or {}).get("ratio")
    base_x, base_y = _placement_beside_selection(selected, canvas_context)

    nodes: list[dict[str, Any]] = []
    for i, prompt in enumerate(prompts):
        params: dict[str, Any] = {
            "prompt": prompt,
            "title": skill.name if count == 1 else f"{skill.name}·{i + 1}",
            "model": IMAGE_PREF_MODEL,
        }
        if ratio:
            params["ratio"] = ratio
        nodes.append({
            "type": "image",
            "creativeType": "keyframe",
            "x": base_x + i * 40,
            "y": base_y + i * 160,
            "params": params,
            "prompt": prompt,
        })

    s_read = _sid("read")
    s_create = _sid("edit")
    steps: list[PlanStep] = [
        PlanStep(
            id=s_read, kind="read", title="读取画布", purpose="确认上下文",
            payload={"tool": "get_canvas_summary", "params": {}},
        ),
        PlanStep(
            id=s_create, kind="edit",
            title=f"创建「{skill.name}」{'三联' if count == 3 else ''}节点",
            purpose=skill.description,
            depends_on=[s_read],
            payload={"tool": "create_nodes", "params": {"nodes": nodes}},
        ),
    ]
    # 选中参考接到第一张（人像/海报风格迁移）；三联图三张都吃同一参考
    dep_after_create = [s_create]
    if selected:
        for i in range(count):
            conn_steps = _steps_connect_selected(
                selected=selected,
                target_created_idx=i,
                depends_on=dep_after_create,
                canvas=canvas_context,
            )
            if conn_steps:
                steps.extend(conn_steps)
                dep_after_create = [conn_steps[-1].id]

    # 三联：按叙事顺序串起来
    if count >= 2:
        chain_edges = [
            {
                "sourceNodeId": f"$created[{i}]",
                "targetNodeId": f"$created[{i + 1}]",
                "dependencyType": "reference",
            }
            for i in range(count - 1)
        ]
        s_chain = _sid("conn-trip")
        steps.append(PlanStep(
            id=s_chain, kind="edit", title="三联叙事顺序连线",
            purpose="用 reference 表达阅读顺序，不阻断各自生成",
            depends_on=dep_after_create,
            payload={"tool": "connect_nodes", "params": {"edges": chain_edges}},
        ))
        dep_after_create = [s_chain]

    for i, prompt in enumerate(prompts):
        steps.append(PlanStep(
            id=_sid(f"exec-{i}"), kind="exec",
            title="提交生成" if count == 1 else f"提交第 {i + 1} 幅",
            purpose="生成画面",
            depends_on=dep_after_create if i == 0 else [steps[-1].id],
            payload={"tool": "submit_generation", "params": {
                "node_id": f"$created[{i}]",
                "model_type": "image",
                "model_params": {"prompt": prompt, "count": 1},
                "estimated_cost": 8,
            }},
        ))

    reply = str(creative.get("reply") or (
        f"已创建「{skill.name}」三联并提交生成。" if count == 3
        else f"已创建「{skill.name}」并提交生成。"
    ))
    if selected and not creative.get("reply"):
        reply = f"已基于选中参考创建「{skill.name}」并提交生成。"
    return StructuredPlan(
        goal=str(creative.get("goal") or f"{skill.name}：{theme}"),
        workflow=skill.key,
        steps=steps,
        completion_criteria=[f"「{skill.name}」节点已提交生成"],
        reply=reply,
        thinking=str(creative.get("thinking") or (
            "Skill 视觉 playbook：选中作 input，产物独立落节点。" if selected else ""
        )),
        next_actions=list(creative.get("next_actions") or []),
    )


def _label_to_spec(label: str) -> tuple[str, str, str]:
    """骨架标签 → (node_type, creative_type, prompt_role)。"""
    if any(k in label for k in ("关键帧", "单图", "海报", "六格", "人像", "三联")):
        return ("image", "keyframe", "image")
    if "视频镜头" in label or ( "视频" in label and "提示" not in label and "脚本" not in label):
        return ("video", "clip", "clip")
    if any(k in label for k in ("配音", "声音", "旁白")):
        return ("audio", "audio", "audio")
    if "合成" in label:
        return ("compose", "composite", "composite")
    if any(k in label for k in ("角色", "一致性", "服装", "表情")):
        return ("text", "character", "character")
    if any(k in label for k in ("分镜", "镜头清单", "镜头提示", "提示词")):
        return ("text", "shot", "shot")
    return ("text", "script", "script")


def _role_prompt(creative: dict[str, Any], role: str, content: str, theme: str, label: str) -> str:
    field = {
        "script": "script_prompt",
        "character": "character_prompt",
        "shot": "storyboard_prompt",
        "composite": "compose_prompt",
        "image": "script_prompt",
        "clip": "compose_prompt",
        "audio": "character_prompt",
    }.get(role, "script_prompt")
    raw = str(creative.get(field) or "").strip()
    if role in ("image", "clip") and creative.get("shots"):
        shot0 = creative["shots"][0] if isinstance(creative["shots"][0], dict) else {}
        raw = str(shot0.get("keyframe_prompt" if role == "image" else "clip_prompt") or raw).strip()
    if not _blank_or_dump(raw, content):
        return raw
    built = build_node_prompt(role=role, user_theme=content, goal=theme)
    return f"{label}：{built}" if built else f"{label}（主题：{theme}）"


def _compile_text_chain(
    content: str,
    skill: SkillDef,
    creative: dict[str, Any],
    *,
    skeleton: list[str],
    no_exec: bool,
    selected_nodes: list[int] | None = None,
    canvas_context: dict[str, Any] | None = None,
) -> StructuredPlan:
    """按 Skill 骨架落文本/单图链路，不套短剧成片脚手架。"""
    theme = extract_theme(content) or str(creative.get("goal") or skill.name)
    labels = skeleton or list(skill.workflow_skeleton)
    selected = [int(x) for x in (selected_nodes or [])]
    base_x, base_y = _placement_beside_selection(
        selected, canvas_context, default_x=140, default_y=160,
    )
    nodes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label in labels:
        ntype, ctype, role = _label_to_spec(label)
        key = (ntype, ctype)
        if key in seen:
            continue
        seen.add(key)
        prompt = _role_prompt(creative, role, content, theme, label)
        params: dict[str, Any] = {"prompt": prompt, "title": label}
        if ntype == "image":
            params["model"] = IMAGE_PREF_MODEL
        if ntype == "video":
            params.update(backfill_video_node_params(params, user_content=content))
        nodes.append({
            "type": ntype,
            "creativeType": ctype,
            "x": base_x + len(nodes) * 220,
            "y": base_y,
            "params": params,
            "prompt": prompt,
        })
    if not nodes:
        return _refuse_empty_scaffold(content, creative)

    steps: list[PlanStep] = []
    s_read = _sid("read")
    steps.append(PlanStep(
        id=s_read, kind="read", title="读取画布现状",
        purpose="确认真实节点，避免编造",
        payload={"tool": "get_canvas_summary", "params": {}},
    ))
    s_create = _sid("edit-chain")
    steps.append(PlanStep(
        id=s_create, kind="edit", title=f"按「{skill.name}」创建 {len(nodes)} 个节点",
        purpose=skill.description,
        depends_on=[s_read],
        payload={"tool": "create_nodes", "params": {"nodes": nodes}},
        idempotency_key=f"skill-chain:{skill.key}:{theme[:40]}",
    ))
    last_dep = [s_create]
    # 选中参考接到首个 image（风格迁移/参考图）；无图则接到链起点
    if selected:
        target_idx = 0
        for i, n in enumerate(nodes):
            if n.get("type") == "image":
                target_idx = i
                break
        conn_sel = _steps_connect_selected(
            selected=selected,
            target_created_idx=target_idx,
            depends_on=last_dep,
            canvas=canvas_context,
        )
        if conn_sel:
            steps.extend(conn_sel)
            last_dep = [conn_sel[-1].id]
    if len(nodes) >= 2:
        edges = [
            {
                "sourceNodeId": f"$created[{i}]",
                "targetNodeId": f"$created[{i + 1}]",
                "dependencyType": "input",
            }
            for i in range(len(nodes) - 1)
        ]
        s_conn = _sid("conn")
        steps.append(PlanStep(
            id=s_conn, kind="edit", title="按骨架顺序连线",
            purpose="上游产物作为下游 input",
            depends_on=last_dep,
            payload={"tool": "connect_nodes", "params": {"edges": edges}},
        ))
        last_dep = [s_conn]
    steps.append(PlanStep(
        id=_sid("layout"), kind="edit", title="整理布局",
        purpose="依赖图可视化",
        depends_on=last_dep,
        payload={"tool": "layout_nodes", "params": {"layout": "auto"}},
    ))
    if not no_exec:
        # 有选中参考时，链起点已有上游，优先提交第一个 image；否则提交文本起点
        exec_idx = 0
        if selected:
            for i, n in enumerate(nodes):
                if n.get("type") == "image":
                    exec_idx = i
                    break
        first_type = nodes[exec_idx].get("type") or "text"
        if first_type in ("text", "image", "audio"):
            cost = {"text": 5, "image": 8, "audio": 10}.get(first_type, 5)
            steps.append(PlanStep(
                id=_sid("exec-root"), kind="exec", title="提交链起点生成",
                purpose="提交可执行起点；有选中参考时优先提交画面节点",
                depends_on=[steps[-1].id],
                payload={
                    "tool": "submit_generation",
                    "params": {
                        "node_id": f"$created[{exec_idx}]",
                        "model_type": first_type,
                        "model_params": {"prompt": nodes[exec_idx].get("prompt"), "count": 1},
                        "estimated_cost": cost,
                    },
                },
            ))
    reply = str(creative.get("reply") or f"已按 Skill「{skill.name}」搭建工作流。")
    if selected and not creative.get("reply"):
        reply = f"已基于选中参考按 Skill「{skill.name}」搭建工作流。"
    return StructuredPlan(
        goal=str(creative.get("goal") or f"{skill.name}：{theme}"),
        workflow=skill.key,
        steps=steps,
        assumptions=list(creative.get("assumptions") or []) + [f"骨架：{' → '.join(labels)}"],
        completion_criteria=list(creative.get("completion_criteria") or [f"已按「{skill.name}」落节点"]),
        reply=reply,
        thinking=str(creative.get("thinking") or f"结构来自 {skill.key} 骨架，内容来自创意规划。"),
        next_actions=list(creative.get("next_actions") or []),
        user_decision_required=bool(creative.get("ask_user")),
        constraints={"ask_question": creative.get("ask_question") or ""},
    )


def compile_execution_plan(
    content: str,
    *,
    intent_name: str,
    requested_skill: str | None,
    creative: dict[str, Any],
    canvas_context: dict[str, Any] | None = None,
    skill_keys: list[str] | None = None,
    selected_nodes: list[int] | None = None,
) -> StructuredPlan:
    from .pipeline import (
        canvas_has_workflow,
        plan_advance_pipeline,
        plan_compose_existing,
        wants_direct_compose,
        wants_rebuild_workflow,
    )

    selected = [int(x) for x in (selected_nodes or [])]

    def _legacy_to_structured(legacy, *, goal: str, workflow: str) -> StructuredPlan:
        steps = [
            PlanStep(
                id=_sid("reuse"),
                kind="exec" if a.tool_name in ("submit_generation", "compose_final", "upscale", "outpaint", "extract_frames", "trim_clip") else (
                    "read" if a.tool_name.startswith(("get_", "list_", "search_")) else "edit"
                ),
                title=a.summary or a.tool_name,
                purpose=a.reasoning or "",
                payload={"tool": a.tool_name, "params": a.params},
            )
            for a in legacy.actions
        ]
        for i in range(1, len(steps)):
            steps[i].depends_on = [steps[i - 1].id]
        return StructuredPlan(
            goal=goal,
            workflow=workflow,
            steps=steps,
            reply=legacy.reply,
            thinking=legacy.thinking or creative.get("thinking") or "",
            completion_criteria=["复用画布已有节点推进"],
            next_actions=list(legacy.next_actions or creative.get("next_actions") or []),
        )

    from .pipeline import wants_new_independent_create
    from ..agent.planner import (
        PlanResult,
        _infer_node_type,
        _plan_create_media,
        _plan_media_process,
        classify_intent,
    )

    # Cookbook 加工意图：扩图/超分/抽帧/剪辑（优先于短剧铁路）
    process_intent = classify_intent(content)
    if process_intent in ("outpaint", "upscale", "extract_frames", "trim_clip"):
        meta = {
            "outpaint": ("扩图（派生新图节点）", "从源图派生扩图，源图保留", 12),
            "upscale": ("超分（派生新节点）", "源与结果分离", 12),
            "extract_frames": ("抽帧（派生新图节点）", "从源视频派生关键帧", 8),
            "trim_clip": ("剪辑（派生新视频节点）", "从源视频派生片段", 8),
        }[process_intent]
        legacy_actions = _plan_media_process(
            content, selected, process_intent,
            summary=meta[0], reasoning=meta[1], estimated_cost=meta[2],
        )
        return _legacy_to_structured(
            PlanResult(
                actions=legacy_actions,
                reply=f"已按「{meta[0]}」规划加工。",
                thinking=str(creative.get("thinking") or meta[1]),
                next_actions=list(creative.get("next_actions") or []),
            ),
            goal=str(creative.get("goal") or meta[0]),
            workflow=f"media_process:{process_intent}",
        )

    # 画布已有链路时：合成/推进优先，禁止再脚手架一套短剧。
    # 但用户明确要「独立新建」时绝不劫持成「成片已就绪」汇报。
    skip_workflow_rails = wants_new_independent_create(content) or wants_rebuild_workflow(content)
    # 有选中参考要派生新媒体时，也不走成片铁路
    if selected and process_intent in ("create", "generate"):
        skip_workflow_rails = True
    if (
        canvas_context
        and canvas_has_workflow(canvas_context)
        and not skip_workflow_rails
    ):
        if wants_direct_compose(content) or ("合成" in (content or "") and "短剧" not in (content or "")):
            return _legacy_to_structured(
                plan_compose_existing(canvas_context),
                goal="复用已有节点合成成片",
                workflow="compose_existing",
            )
        if intent_name == "advance_pipeline":
            return _legacy_to_structured(
                plan_advance_pipeline(canvas_context, selected),
                goal="推进未完成流程",
                workflow="advance_pipeline",
            )
        creative_counts = (canvas_context or {}).get("creativeTypeCounts") or {}
        type_counts = (canvas_context or {}).get("nodeTypeCounts") or {}
        clips = int(creative_counts.get("clip") or type_counts.get("video") or 0)
        compose = int(creative_counts.get("composite") or type_counts.get("compose") or 0)
        if clips >= 2 or compose >= 1:
            return _legacy_to_structured(
                plan_advance_pipeline(canvas_context, selected),
                goal="推进已有工作流",
                workflow="advance_pipeline",
            )

    # 简单独立媒体创建 / 选中参考派生：不依赖创意 LLM，直接落节点+连线+提交
    # 若已指定视觉/文本 Skill，交给后续 Skill 编译，避免「电影海报」被降成裸 create
    ntype = _infer_node_type(content)
    early_keys = list(skill_keys or []) or resolve_route_keys(requested_skill)
    if not early_keys:
        early_keys = resolve_route_keys(str(creative.get("selected_skill") or creative.get("workflow") or ""))
    early_profile = compile_profile_for(primary_skill_key(early_keys))
    skill_owns_compile = early_profile in ("simple_visual", "text_chain", "short_drama")

    looks_like_simple_media = (
        wants_new_independent_create(content)
        and ntype in ("image", "video", "audio")
        and not re.search(r"短剧|分镜|工作流|链路|六格|海报项目", content or "", re.I)
    ) or (
        intent_name == "direct_canvas_action"
        and ntype in ("image", "video", "audio")
    ) or (
        # 有选中参考 + 要出图/视频 → 派生链路
        bool(selected)
        and ntype in ("image", "video", "audio")
        and process_intent in ("create", "generate", "general")
        and not re.search(r"短剧|分镜|工作流|链路", content or "", re.I)
    )
    if looks_like_simple_media and not skill_owns_compile:
        legacy_actions = _plan_create_media(content, selected, canvas_context)
        if legacy_actions:
            reply = (
                f"已基于选中参考创建{ntype}节点并提交生成。"
                if selected
                else f"已创建独立{ntype}节点并提交生成。"
            )
            return _legacy_to_structured(
                PlanResult(
                    actions=legacy_actions,
                    reply=reply,
                    thinking=str(creative.get("thinking") or (
                        "选中参考派生，源与结果分离。" if selected else "独立单点创建，不走成片/短剧铁路。"
                    )),
                    next_actions=list(creative.get("next_actions") or []),
                ),
                goal=str(creative.get("goal") or extract_theme(content) or "独立创建"),
                workflow="simple_media_create",
            )

    trim = infer_trim_from_user(content)
    # 合并 LLM 裁剪
    for key in ("skip_steps", "stop_after", "start_from"):
        if creative.get(key):
            if key == "skip_steps":
                trim["skip_labels"] = list(set(trim["skip_labels"] + list(creative["skip_steps"])))
            else:
                trim[key] = creative[key]

    no_exec = "__no_exec__" in trim["skip_labels"]
    trim["skip_labels"] = [x for x in trim["skip_labels"] if x != "__no_exec__"]

    keys = list(skill_keys or []) or resolve_route_keys(requested_skill)
    if not keys:
        keys = resolve_route_keys(str(creative.get("selected_skill") or creative.get("workflow") or ""))
    primary_key = primary_skill_key(keys)
    primary = get_skill(primary_key) if primary_key else None
    profile = compile_profile_for(primary_key)

    if intent_name == "regenerate_stale":
        from .pipeline import plan_reregenerate_stale
        legacy = plan_reregenerate_stale(canvas_context)
        steps = [
            PlanStep(
                id=_sid("legacy"),
                kind="exec" if a.tool_name == "submit_generation" else (
                    "read" if a.tool_name.startswith("get_") else "edit"
                ),
                title=a.summary or a.tool_name,
                purpose=a.reasoning or "",
                payload={"tool": a.tool_name, "params": a.params},
            )
            for a in legacy.actions
        ]
        # 串行依赖
        for i in range(1, len(steps)):
            steps[i].depends_on = [steps[i - 1].id]
        return StructuredPlan(
            goal="重跑过期节点",
            workflow="regenerate_stale",
            steps=steps,
            reply=legacy.reply,
            thinking=legacy.thinking,
            completion_criteria=["过期节点已按依赖顺序重跑"],
        )

    if intent_name == "advance_pipeline":
        from .pipeline import plan_advance_pipeline
        legacy = plan_advance_pipeline(canvas_context)
        steps = [
            PlanStep(
                id=_sid("adv"),
                kind="exec" if a.tool_name in ("submit_generation", "compose_final") else (
                    "read" if a.tool_name.startswith(("get_", "list_", "search_")) else "edit"
                ),
                title=a.summary or a.tool_name,
                purpose=a.reasoning or "",
                payload={"tool": a.tool_name, "params": a.params},
            )
            for a in legacy.actions
        ]
        for i in range(1, len(steps)):
            steps[i].depends_on = [steps[i - 1].id]
        return StructuredPlan(
            goal="推进未完成流程",
            workflow="advance_pipeline",
            steps=steps,
            reply=legacy.reply,
            thinking=legacy.thinking,
            completion_criteria=["已推进一层可执行产物"],
        )

    if profile == "simple_visual" and primary:
        return _compile_simple_visual(
            content, primary, creative,
            selected_nodes=selected,
            canvas_context=canvas_context,
        )

    if profile == "text_chain" and primary:
        skeleton = list(primary.workflow_skeleton)
        skeleton = trim_skeleton(
            skeleton,
            skip_labels=trim["skip_labels"],
            stop_after=trim.get("stop_after"),
            start_from=trim.get("start_from"),
        )
        return _compile_text_chain(
            content, primary, {**creative, "skip_steps": trim["skip_labels"]},
            skeleton=skeleton, no_exec=no_exec,
            selected_nodes=selected,
            canvas_context=canvas_context,
        )

    if profile != "short_drama" and not _has_llm_creative_payload(creative):
        return _refuse_empty_scaffold(content, creative)

    # 短剧：仅当主 Skill 是 vertical-short-drama，或创意里已有镜头级内容
    skeleton = list(primary.workflow_skeleton) if primary else []
    skeleton = trim_skeleton(
        skeleton,
        skip_labels=trim["skip_labels"],
        stop_after=trim.get("stop_after"),
        start_from=trim.get("start_from"),
    )
    creative = {
        **creative,
        "skip_steps": trim["skip_labels"],
        "stop_after": trim.get("stop_after"),
        "start_from": trim.get("start_from"),
    }
    plan = _compile_short_drama(content, creative, no_exec=no_exec)
    if skeleton:
        plan.assumptions = list(plan.assumptions) + [f"裁剪后骨架：{' → '.join(skeleton)}"]
    if primary:
        plan.workflow = primary.key
    return plan


def build_structured_plan(
    content: str,
    *,
    intent: dict[str, Any],
    skill_keys: list[str],
    canvas_context: dict[str, Any] | None,
    api_key: str | None,
    base_url: str = "",
    model: str = "",
    recent_messages: list[dict[str, Any]] | None = None,
    project_memories: list[dict[str, Any]] | None = None,
    long_term_prefs: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    selected_nodes: list[int] | None = None,
) -> StructuredPlan:
    keys = list(skill_keys or []) or resolve_route_keys(intent.get("requested_skill"))
    primary = get_skill(primary_skill_key(keys) or "")
    skeleton = list(primary.workflow_skeleton) if primary else []
    trim = infer_trim_from_user(content)
    skeleton = trim_skeleton(
        skeleton,
        skip_labels=[x for x in trim["skip_labels"] if x != "__no_exec__"],
        stop_after=trim.get("stop_after"),
        start_from=trim.get("start_from"),
    )
    bundle = skill_instructions_bundle(keys)

    theme = extract_theme(content) or ""
    creative: dict[str, Any] = {
        "goal": theme or "创作任务",
        "thinking": "无 LLM：不灌空模板壳；仅在用户主题足够具体时按角色写生成指令。",
        "reply": "",
        "shots": [],
        "skip_steps": trim["skip_labels"],
        "stop_after": trim.get("stop_after"),
        "start_from": trim.get("start_from"),
    }

    if api_key and intent.get("name") in (
        "workflow_orchestration", "edit_existing", "unknown", "direct_canvas_action",
    ):
        try:
            llm_creative = creative_plan_llm(
                content=content,
                intent=intent,
                skill_instructions=bundle,
                canvas_context=canvas_context,
                skeleton=skeleton,
                api_key=api_key,
                base_url=base_url,
                model=model,
                recent_messages=recent_messages,
                project_memories=project_memories,
                long_term_prefs=long_term_prefs,
                observations=observations,
            )
            merged = {**creative, "from_llm": True}
            if isinstance(llm_creative, dict):
                for key, val in llm_creative.items():
                    if val is None or val == "" or val == []:
                        continue
                    merged[key] = val
            if creative.get("skip_steps") and not merged.get("skip_steps"):
                merged["skip_steps"] = list(creative["skip_steps"])
            for key in ("stop_after", "start_from"):
                if creative.get(key) and not merged.get(key):
                    merged[key] = creative[key]
            creative = _expand_role_prompts(merged, content, theme)
        except Exception as exc:
            creative["thinking"] = f"创意规划降级：{str(exc)[:120]}"
            creative = _expand_role_prompts(creative, content, theme)
    else:
        creative = _expand_role_prompts(creative, content, theme)

    if not keys:
        picked = resolve_route_keys(str(creative.get("selected_skill") or creative.get("workflow") or ""))
        if picked:
            keys = picked

    return compile_execution_plan(
        content,
        intent_name=str(intent.get("name") or "workflow_orchestration"),
        requested_skill=intent.get("requested_skill") or (primary_skill_key(keys) if keys else None),
        creative=creative,
        canvas_context=canvas_context,
        skill_keys=keys,
        selected_nodes=selected_nodes,
    )


def steps_to_planned_actions(plan: StructuredPlan) -> list[dict[str, Any]]:
    """桥接旧 executor：把 ready/planned 步骤展平为 PlannedActionDict。"""
    out = []
    for step in plan.steps:
        if step.status in ("succeeded", "skipped", "cancelled"):
            continue
        tool = step.payload.get("tool")
        if not tool:
            continue
        out.append({
            "tool_name": tool,
            "params": dict(step.payload.get("params") or {}),
            "summary": step.title,
            "reasoning": step.purpose,
            "status": "pending",
            "step_id": step.id,
        })
    return out
