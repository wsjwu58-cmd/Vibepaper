"""节点 Prompt 构建。

核心原则（用户契约）：
1. 用户要求定方向 —— 每个节点的题材/情绪来自用户（或总脚本/分镜产出）；
2. 上游产出定形象 —— 构图/长相/光线通过 input 连线自动喂入（reference），不靠复制文本；
3. 节点 Prompt 定本次动作 —— 只写本节点新增内容（静帧构图 / 运镜动作 / 旁白句），
   绝不把上游整段产出原文粘进下游 Prompt。
"""

from __future__ import annotations

import re
from typing import Any

# 镜头节拍：bootstrap 时尚无分镜产出时，按镜号给出差异化方向
_SHOT_BEATS = (
    "开场：建立场景与氛围，主角入画，交代空间关系",
    "冲突：对立双方对峙或交汇，情绪升温",
    "转折：动作顶点或关系变化，留下余韵",
    "收束：情绪落地或新的悬念",
)


def extract_theme(user_content: str, max_len: int = 200) -> str:
    """从用户消息提取创作主题（去掉指令壳，保留主体）。"""
    text = (user_content or "").strip()
    # 「按照工作流生成橘猫…」→ 保留「橘猫…」，勿用 工作流.*$ 切掉后半段
    text = re.sub(
        r"^(按照|按|用)?(工作流|流程|链路|分镜链)?(来)?(帮我|请|麻烦)?"
        r"(生成|做|制作|创建|搭建|编排|写)?",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(
        r"(添加到画布|写入画布|到画布上|画布上|分镜链)$",
        "",
        text,
        flags=re.I,
    ).strip(" ，,。；;")
    if not text:
        text = (user_content or "").strip()
    return text[:max_len]


def extract_visual_goal(user_content: str, max_len: int = 160) -> str:
    """从用户指令中提取画面主体，去掉流程词。"""
    text = (user_content or "").strip()
    text = re.sub(r"^先", "", text).strip()
    text = re.sub(
        r"(再|然后|接着|之后|完成后)(.{0,12})?(生成|做|制作|创建)(.{0,6})?(视频|短片|动画|镜头).*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(根据|基于|用|参考)(.{0,8})?(这张?|该)?(图片|图|首帧|形象)(来?)?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(帮我|请|麻烦|想要|我要|按照工作流)?(生成|做|制作|创建|出)",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(
        r"(的)?(一张?|一段?|一个?)?(图片|图|视频|短片|动画|镜头|短剧)$",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"^[，,、\s]+|[，,、\s]+$", "", text).strip()
    theme = text or extract_theme(user_content)
    return theme[:max_len]


def _motion_hint(shot_index: int | None) -> str:
    hints = ["缓慢推近", "固定机位微动", "横移跟拍", "轻微环绕", "从特写缓慢拉远", "从高往下俯拍"]
    if shot_index is None:
        return "平稳推近或固定机位"
    return hints[(shot_index - 1) % len(hints)]


def _shot_beat(shot_index: int | None) -> str:
    if not shot_index:
        return _SHOT_BEATS[0]
    return _SHOT_BEATS[(shot_index - 1) % len(_SHOT_BEATS)]


def build_node_prompt(
    *,
    role: str,
    user_theme: str = "",
    shot_index: int | None = None,
    shot_count: int | None = None,
    duration: int = 5,
    tone: str = "沉稳、有叙事感",
    goal: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    """为单个节点生成独立 Prompt。

    - script/shot/character/text：整合用户方向的创作简报（发给文本模型产出正文）
    - keyframe/image：只写本镜静帧画面（形象细节由方向给出，不写运镜）
    - clip/video：只写本次运镜/动作；形象靠上游首帧 reference，不复述外貌
    """
    theme = extract_theme(user_theme)
    direction = goal or theme or "见用户创作意图"
    n = shot_index or 1
    total = shot_count or 3
    motion = _motion_hint(shot_index)
    beat = _shot_beat(shot_index)
    extra = extra or {}

    if role == "script":
        return (
            f"请直接写出短剧【总脚本】正文（不要复述指令）。\n"
            f"创作方向：{direction}\n"
            f"必须包含：主要人物与关系、核心冲突、视觉基调、情绪弧线；"
            f"300–500 字，可被拆成 {total} 个镜头。\n"
            f"开篇即进入故事，勿写「主题：」「要求：」这类元说明。"
        )

    if role == "character":
        return (
            f"请直接写出【角色卡】正文（可落地的视觉规格）。\n"
            f"创作方向：{direction}\n"
            f"覆盖：外观（体型/毛色或肤色/服装/标志道具）、性格关键词 2–3 个、"
            f"跨镜头一致性约束。不要抄写总脚本原文。"
        )

    if role == "shot":
        return (
            f"请直接输出【分镜表】，严格 {total} 行，每行格式：\n"
            f"镜号 | 景别 | 画面描述 | 运镜 | 时长(秒)\n"
            f"创作方向：{direction}\n"
            f"人物与基调对齐上游总脚本（由参考文本提供）；"
            f"不要跳镜、不要合并多镜、不要粘贴脚本原文。"
        )

    if role == "keyframe":
        # 静帧：写本镜画面方向；上游分镜/角色通过 reference 喂入，不在此粘贴全文
        return (
            f"镜头{n}首帧（静帧，禁止运镜/动态描述）。\n"
            f"故事方向：{direction}\n"
            f"本镜节拍：{beat}\n"
            f"说清：主体位置、景别、光影、色彩；与分镜第 {n} 镜对齐。"
            f"形象细节以参考栏上游（分镜/角色卡）为准，勿整段复述脚本。"
        )

    if role == "clip":
        # 视频：只写本次动作；形象由首帧 reference 锁定
        return (
            f"镜头{n}视频（图生视频）。\n"
            f"运镜与动作：{motion}，时长约 {duration} 秒；节拍：{beat}。\n"
            f"延续首帧的构图、形象与光线，只描述本次新增的运动与情绪变化；"
            f"不要复述角色外貌或重写整段故事。"
        )

    if role == "audio":
        return (
            f"为短剧撰写旁白/配音文案。\n"
            f"方向：{direction}\n"
            f"语气：{tone}；与分镜节奏对齐，每句对应一镜或一组镜头。"
        )

    if role == "composite":
        return (
            f"按镜号顺序拼接 {total} 段视频成片。"
            f"镜头间硬切，片头片尾可淡入淡出；保持色调一致。"
        )

    if role == "image":
        return (
            f"画面主体：{direction}\n"
            f"说清外形、姿态、场景、光影与风格；静帧构图完整，可单独成图。"
            f"禁止运镜描述。"
        )

    if role == "video":
        return (
            f"画面内容方向：{direction}\n"
            f"运镜：{motion}；时长约 {duration} 秒。"
            f"若有首帧参考图，延续其形象与光线，只写本次动态。"
        )

    if role == "text":
        return (
            f"产出方向：{direction}\n"
            f"结构清晰，可直接作为下游节点的上下文参考；开篇即进入正文。"
        )

    # fallback
    return f"创作方向：{direction}"


def prompt_for_image_then_video(user_content: str, *, duration: int = 5) -> tuple[str, str]:
    """图→视频：图写静帧方向，视频只写运镜（形象靠首帧 reference）。"""
    goal = extract_visual_goal(user_content) or extract_theme(user_content)
    image_prompt = build_node_prompt(role="image", user_theme=user_content, goal=goal)
    video_prompt = build_node_prompt(
        role="video",
        user_theme=user_content,
        goal=goal,
        duration=duration,
    )
    return image_prompt, video_prompt


def ensure_node_prompt(node: dict, user_content: str = "") -> dict:
    """create_nodes 兜底：节点缺少 prompt 时按 type/creativeType 自动补全。"""
    out = dict(node)
    params = dict(out.get("params") or out.get("config") or {})
    existing = str(out.get("prompt") or params.get("prompt") or "").strip()
    if len(existing) >= 20:
        return out
    ntype = str(out.get("type") or "text")
    creative = str(out.get("creativeType") or out.get("creative_type") or "")
    role_map = {
        "keyframe": "keyframe",
        "clip": "clip",
        "script": "script",
        "shot": "shot",
        "character": "character",
        "composite": "composite",
        "audio": "audio",
    }
    role = role_map.get(creative) or {
        "image": "image",
        "video": "video",
        "audio": "audio",
        "text": "text",
    }.get(ntype, "text")
    filled = build_node_prompt(
        role=role,
        user_theme=user_content or existing,
        goal=extract_visual_goal(user_content) if user_content else existing,
    )
    params["prompt"] = filled
    if not params.get("title"):
        params["title"] = extract_visual_goal(user_content)[:40] or filled[:40]
    out["params"] = params
    out["prompt"] = filled
    return out


def prompt_for_media_create(user_content: str, node_type: str, creative_type: str | None = None) -> str:
    """单节点创建时的 Prompt。"""
    goal = (extract_visual_goal(user_content) or extract_theme(user_content))[:120]
    if node_type == "video":
        return build_node_prompt(
            role="video", user_theme=user_content, goal=goal or "短视频片段", duration=5,
        )
    if node_type == "image":
        return build_node_prompt(
            role="image", user_theme=user_content, goal=goal or "画面主体",
        )
    if node_type == "audio":
        return build_node_prompt(role="audio", user_theme=user_content)
    if node_type == "text":
        return build_node_prompt(role="text", user_theme=user_content, goal=goal)
    role = creative_type or "text"
    if role in ("keyframe", "clip"):
        return build_node_prompt(
            role=role, user_theme=user_content, shot_index=1, shot_count=1, goal=goal,
        )
    return build_node_prompt(role=role, user_theme=user_content, goal=goal)


def _upstream_text_snippet(node: dict, max_len: int = 240) -> str:
    params = node.get("params") or {}
    out = node.get("output")
    if isinstance(out, dict):
        text = str(out.get("text") or out.get("content") or "").strip()
        if text:
            return text[:max_len]
    for key in ("lastOutputText", "text", "content"):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:max_len]
    return ""


def refine_prompt_on_submit(node: dict, canvas_context: dict | None = None) -> str:
    """提交前：保留节点专属 Prompt；若过短则按角色重建。不把上游全文粘进去。"""
    params = node.get("params") or {}
    existing = str(node.get("prompt") or params.get("prompt") or "").strip()
    creative = str(node.get("creativeType") or node.get("creative_type") or "")
    ntype = str(node.get("type") or "")
    title = str(params.get("title") or "")
    m = re.search(r"镜头(\d+)", title)
    shot_index = int(m.group(1)) if m else None

    # 旧机械模板（【总脚本】主题：…）强制重写；新格式创意简报保留
    mechanical = bool(re.match(
        r"^【(总脚本|分镜表|角色卡|镜头\d+|图片生成|视频生成|配音|成片)",
        existing,
    ))
    if len(existing) >= 24 and not mechanical:
        return existing

    role = creative or ntype
    if role not in (
        "script", "shot", "character", "keyframe", "clip",
        "audio", "composite", "image", "video", "text",
    ):
        role = "text" if ntype == "text" else ntype

    # 方向：优先节点已有主题词 / 标题，否则从上游文本抽一句
    direction = extract_theme(existing) if existing else ""
    if len(direction) < 4:
        direction = title
    if canvas_context and len(direction) < 4:
        for up in (canvas_context.get("nodes") or []):
            snippet = _upstream_text_snippet(up)
            if snippet:
                direction = snippet[:80]
                break

    return build_node_prompt(
        role=role if role else "text",
        user_theme=direction,
        goal=direction,
        shot_index=shot_index,
    )


def enrich_submit_prompt(node: dict, canvas_context: dict | None = None) -> str:
    return refine_prompt_on_submit(node, canvas_context)


def user_theme_is_verbatim(prompt: str, node: dict) -> bool:
    return False
