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


def _norm_cmp(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def is_verbatim_user_dump(prompt: str, user_content: str) -> bool:
    """节点 prompt 是否只是用户原话/主题原样粘贴（禁止作为工作流节点正文）。"""
    p = _norm_cmp(prompt)
    u = _norm_cmp(user_content)
    if not p or not u or len(p) < 4:
        return False
    if p == u:
        return True
    theme = _norm_cmp(extract_theme(user_content))
    if theme and p == theme:
        return True
    goal = _norm_cmp(extract_visual_goal(user_content))
    if goal and p == goal:
        return True
    # 「主题（角色设定）」这类只加短后缀的粘贴
    if theme and theme in p and len(p) <= len(theme) + 16:
        return True
    return False


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
    """按节点角色写生成指令：主题只作题材，禁止把用户原话当成节点 prompt。

    具体剧情/对白/构图正文优先由 Creative Planner（LLM）填写；本函数是角色化兜底。
    """
    theme = extract_theme(user_theme)
    direction = (goal or theme or "").strip()
    n = shot_index or 1
    total = shot_count or 3
    motion = _motion_hint(shot_index)
    beat = _shot_beat(shot_index)
    _ = extra or {}

    if not direction:
        return ""

    if role == "script":
        return (
            f"写总脚本（主题：{direction}）。"
            f"给出人物关系、本集冲突、可表演对白、场景动作与集尾钩子。"
            f"不要复述用户原指令，不要写工作流步骤。"
        )
    if role == "character":
        return (
            f"写角色卡（主题：{direction}）：外形、服装、辨识特征、跨镜一致性约束。"
            f"不要复制用户原话。"
        )
    if role == "shot":
        return (
            f"把「{direction}」拆成 {total} 个可执行镜头："
            f"镜号、景别、动作、对白要点。每镜独立可画。"
        )
    if role == "keyframe":
        return (
            f"镜头{n}/{total}静帧（主题：{direction}）。节拍：{beat}。"
            f"写构图、光影、主体姿态；不要复述用户整句指令。"
        )
    if role == "clip":
        # 镜头视频：形象靠上游首帧 reference；prompt 只写运镜与节拍
        return (
            f"镜头{n}：{motion}，约 {duration}s。{beat}。"
            f"严格延续参考首帧的主体、构图、服装与色调，只增加自然动态，勿重新创造形象。"
        )
    if role == "audio":
        return f"旁白/配音（主题：{direction}），语气：{tone}。写可录制的短句，不要复述用户原指令。"
    if role == "composite":
        return f"按镜号顺序拼接 {total} 段成片，硬切，色调与叙事连贯。主题方向：{direction}。"
    if role == "image":
        return f"静帧画面（主题：{direction}）。构图清晰，主体完整，光影明确。不要复述用户原指令。"
    if role == "video":
        return (
            f"短视频（主题：{direction}）。运镜：{motion}，约 {duration}s。"
            f"只写动态与镜头运动，不要把用户原话当旁白。"
        )
    if role == "text":
        return f"按主题「{direction}」写出本节点应交付的文本，不要复述用户原指令。"
    return (
        f"按角色「{role}」生成（主题：{direction}）。不要复述用户原指令。"
    )


def ensure_node_prompt(node: dict, user_content: str = "") -> dict:
    """create_nodes 兜底：缺 prompt 或原样粘贴用户指令时，按节点角色重写。"""
    out = dict(node)
    params = dict(out.get("params") or out.get("config") or {})
    existing = str(out.get("prompt") or params.get("prompt") or "").strip()
    role = str(
        out.get("creativeType") or out.get("creative_type") or out.get("type") or "text"
    )
    dumped = bool(user_content) and is_verbatim_user_dump(existing, user_content)
    if len(existing) >= 8 and not dumped:
        return out
    filled = build_node_prompt(role=role, user_theme=user_content)
    if not filled:
        filled = (extract_visual_goal(user_content) or extract_theme(user_content) or "").strip()
    if not filled:
        return out
    params["prompt"] = filled
    if not params.get("title"):
        params["title"] = (extract_theme(user_content) or filled)[:40]
    out["params"] = params
    out["prompt"] = filled
    return out


def prompt_for_image_then_video(user_content: str, *, duration: int = 5) -> tuple[str, str]:
    """图→视频：图写静帧方向；视频只写运镜 + 忠实首帧（形象靠 firstFrameUrl，不靠重述主体）。"""
    goal = extract_visual_goal(user_content) or extract_theme(user_content)
    image_prompt = build_node_prompt(role="image", user_theme=user_content, goal=goal)
    motion = _motion_hint(None)
    # 刻意不把 goal 再写进视频 prompt，避免文生漂移盖过参考图
    video_prompt = (
        f"运镜：{motion}，约 {duration}s。"
        f"严格保持与参考首帧同一主体、构图、服装与色调；只增加自然动态，勿重新创造形象。"
    )
    if goal:
        video_prompt = f"{goal}。{video_prompt}"
    return image_prompt, video_prompt


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
