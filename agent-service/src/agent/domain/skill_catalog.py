"""固化 Skill 目录：骨架模板 + 触发语义（给 LLM / select_skill，不是关键词路由表）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SkillDef:
    key: str
    name: str
    category: str
    description: str
    trigger_semantics: str
    workflow_skeleton: tuple[str, ...]
    instructions: str
    default_constraints: dict[str, Any] = field(default_factory=dict)


# 组合路由：用户任务形态 → 要加载的 Skill key 序列（仍可被用户裁剪）
SKILL_ROUTES: dict[str, tuple[str, ...]] = {
    "竖屏短剧": (
        "manga-story-bible",
        "character-consistency",
        "vertical-short-drama",
        "dialogue-polish",
        "storyboard-shot-list",
        "continuity-review",
    ),
    "六格漫画": ("six-panel-comic", "character-consistency"),
    "电影海报": ("film-poster",),
    "电影感单图": ("cinematic-still",),
    "电影感三联图": ("cinematic-triptych",),
    "短视频脚本": ("short-video-script", "storyboard-shot-list"),
    "长文改编": ("longform-to-short",),
}


SKILL_CATALOG: dict[str, SkillDef] = {
    "vertical-short-drama": SkillDef(
        key="vertical-short-drama",
        name="竖屏短剧单集生成",
        category="短剧/漫剧",
        description="1-3 分钟竖屏单集，强调冲突、反转、集尾钩子",
        trigger_semantics="用户要做竖屏短剧单集、短剧一集、带冲突反转的竖屏剧情，而不是单张海报或纯讨论排版。",
        workflow_skeleton=(
            "项目简报",
            "故事圣经",
            "角色一致性规范",
            "单集剧本",
            "对白润色",
            "分镜与镜头清单",
            "关键帧",
            "视频镜头",
            "配音/声音",
            "合成",
            "连续性审校",
        ),
        instructions=(
            "按骨架推进竖屏短剧；用户可裁剪步骤（跳过角色卡、只要剧本、已有剧本从分镜起）。\n"
            "必须拆镜头级节点，禁止长脚本直接塞进单个 Video。\n"
            "内容（情节/对白/镜头语言）由创意规划生成；结构与依赖由执行编译落实。"
        ),
        default_constraints={"ratio": "9:16", "duration_hint": "1-3min_episode"},
    ),
    "manga-story-bible": SkillDef(
        key="manga-story-bible",
        name="漫剧故事圣经",
        category="短剧/漫剧",
        description="世界观、角色设定、人物关系、长期剧情圣经",
        trigger_semantics="用户要世界观/人物关系/长期剧情设定，而不是立刻生成成片。",
        workflow_skeleton=("世界观", "角色设定", "人物关系", "长期剧情线"),
        instructions="产出可复用的故事圣经文本节点；后续单集与分镜以之为 input 依赖。",
    ),
    "longform-to-short": SkillDef(
        key="longform-to-short",
        name="长内容短剧化改编",
        category="短剧/漫剧",
        description="小说/文章/长剧本 → 竖屏短剧或漫剧集数大纲",
        trigger_semantics="用户提供长文/小说并要求改编成短剧或分集大纲。",
        workflow_skeleton=("素材摘要", "集数大纲", "单集冲突点"),
        instructions="先改编为集数大纲文本节点，再按用户指令进入单集或分镜。",
    ),
    "dialogue-polish": SkillDef(
        key="dialogue-polish",
        name="短剧对白润色",
        category="短剧/漫剧",
        description="生硬对白改写成有区分度、有情绪张力的台词",
        trigger_semantics="用户要改台词/对白润色，而非新建整条短剧链路。",
        workflow_skeleton=("读取原对白", "润色稿", "回写或新建文本节点"),
        instructions="保留人物声口差异与冲突张力；缺原文时先 read/query。",
    ),
    "continuity-review": SkillDef(
        key="continuity-review",
        name="连续剧一致性审校",
        category="短剧/漫剧",
        description="检查剧情、角色、时间线、道具、视觉连续性并给修复方案",
        trigger_semantics="用户要审校连续性、找穿帮、检查前后镜头一致性。",
        workflow_skeleton=("核对画布产物", "问题清单", "修复建议/修补步骤"),
        instructions="讨论态只给方案；指令态可规划修补 edit/exec。",
    ),
    "short-video-script": SkillDef(
        key="short-video-script",
        name="短视频完整脚本",
        category="分镜/脚本",
        description="主题 → 15秒-3分钟完整脚本（口播/画面/字幕/节奏点）",
        trigger_semantics="用户要短视频完整脚本（口播+画面+字幕），不是长剧故事圣经。",
        workflow_skeleton=("主题确认", "完整脚本", "节奏点标注"),
        instructions="脚本按节奏点分段，便于后续拆分镜。",
    ),
    "storyboard-shot-list": SkillDef(
        key="storyboard-shot-list",
        name="分镜与镜头清单",
        category="分镜/脚本",
        description="剧本 → 可执行分镜表、镜头清单、AI 视频提示词",
        trigger_semantics="用户要分镜表/镜头清单/逐镜视频提示词；理解短视频脚本→分镜→镜头链路，而非关键词匹配「分镜」二字。",
        workflow_skeleton=("剧本", "分镜表", "镜头清单", "逐镜视频提示词"),
        instructions="每个镜头独立可生成；下游 keyframe/clip 一对一映射。",
    ),
    "cinematic-still": SkillDef(
        key="cinematic-still",
        name="电影感单图",
        category="视觉设计",
        description="单幅电影镜头感/概念画面（默认走风格迁移）",
        trigger_semantics="用户要一张电影感静帧/概念图，不是三联或短剧链路。",
        workflow_skeleton=("概念确认", "单图节点", "生成"),
        instructions="单 image 节点即可；需要角色一致时叠加角色卡依赖。",
    ),
    "cinematic-triptych": SkillDef(
        key="cinematic-triptych",
        name="电影感三联图",
        category="视觉设计",
        description="连续叙事关系的三联画面",
        trigger_semantics="用户要三张有连续叙事关系的画面。",
        workflow_skeleton=("叙事节拍", "三图节点", "生成"),
        instructions="三张图独立节点，叙事顺序用标题/连线表达。",
    ),
    "film-poster": SkillDef(
        key="film-poster",
        name="电影海报",
        category="视觉设计",
        description="竖版 9:16 中文电影海报（底图+字体分层）",
        trigger_semantics="用户要电影海报、竖版海报，不是六格漫画。",
        workflow_skeleton=("文案/标题", "底图", "字体分层说明"),
        instructions="默认竖版 9:16；文案与画面可分节点。",
        default_constraints={"ratio": "9:16"},
    ),
    "minimal-poster": SkillDef(
        key="minimal-poster",
        name="极简海报",
        category="视觉设计",
        description="大留白、做旧纸张、实验排版的编辑海报",
        trigger_semantics="用户要极简/编辑感/大留白海报。",
        workflow_skeleton=("概念", "海报图"),
        instructions="强调留白与排版意图，避免堆特效。",
    ),
    "six-panel-comic": SkillDef(
        key="six-panel-comic",
        name="六格漫画",
        category="视觉设计",
        description="人物一致、对白简短的 2×3 单页连环漫画",
        trigger_semantics="用户要生成六格漫画/2×3 连环画；若只问「怎么排版」则为讨论不执行。",
        workflow_skeleton=("角色一致", "六格分镜文案", "单页或六格图"),
        instructions="人物一致优先；对白简短；可与角色一致性 Skill 组合。",
    ),
    "lifestyle-portrait": SkillDef(
        key="lifestyle-portrait",
        name="生命感人像",
        category="视觉设计",
        description="游客照/废片 → 高级生活感人像摄影",
        trigger_semantics="用户要做人像质感提升/生活感写真风格化。",
        workflow_skeleton=("参考图", "人像生成/重绘"),
        instructions="有参考图时用 input 依赖；无参考则按描述生成。",
    ),
    "character-consistency": SkillDef(
        key="character-consistency",
        name="AI角色一致性控制",
        category="角色/规范",
        description="角色卡、服装表、表情表、一致性提示词",
        trigger_semantics="用户要角色卡/服装表/表情表/跨镜角色一致，而不是单次出图。",
        workflow_skeleton=("角色卡", "服装表", "表情表", "一致性提示词"),
        instructions="角色卡作为下游镜头的 input；禁止把外貌长文复制进每个镜头 prompt。",
    ),
}


def catalog_summary_for_prompt(limit: int = 20) -> str:
    lines = ["可用 Skill 目录（按语义选择，禁止关键词硬匹配）："]
    for i, skill in enumerate(SKILL_CATALOG.values()):
        if i >= limit:
            break
        skeleton = " → ".join(skill.workflow_skeleton[:6])
        if len(skill.workflow_skeleton) > 6:
            skeleton += " → …"
        lines.append(
            f"- [{skill.key}] {skill.name}（{skill.category}）：{skill.description}\n"
            f"  触发：{skill.trigger_semantics}\n"
            f"  骨架：{skeleton}"
        )
    lines.append("组合路由示例：" + "；".join(f"{k}→{list(v)}" for k, v in list(SKILL_ROUTES.items())[:4]))
    return "\n".join(lines)


def get_skill(key: str) -> SkillDef | None:
    return SKILL_CATALOG.get(key)


def resolve_route_keys(route_or_key: str | None) -> list[str]:
    if not route_or_key:
        return []
    if route_or_key in SKILL_ROUTES:
        return list(SKILL_ROUTES[route_or_key])
    if route_or_key in SKILL_CATALOG:
        return [route_or_key]
    # 名称模糊：中文名
    for skill in SKILL_CATALOG.values():
        if skill.name == route_or_key or skill.name in route_or_key:
            return [skill.key]
    for route_name, keys in SKILL_ROUTES.items():
        if route_name in route_or_key:
            return list(keys)
    return []


def skill_instructions_bundle(keys: list[str]) -> str:
    parts: list[str] = []
    for key in keys:
        skill = SKILL_CATALOG.get(key)
        if not skill:
            continue
        parts.append(
            f"## Skill: {skill.name} ({skill.key})\n"
            f"{skill.description}\n"
            f"骨架：{' → '.join(skill.workflow_skeleton)}\n"
            f"{skill.instructions}"
        )
    return "\n\n".join(parts)


# 组合路由里排在前面的往往是辅助 Skill（圣经/角色卡）；编译要以「主产物」Skill 为准。
_PRIMARY_PRIORITY: tuple[str, ...] = (
    "vertical-short-drama",
    "six-panel-comic",
    "cinematic-triptych",
    "film-poster",
    "cinematic-still",
    "minimal-poster",
    "lifestyle-portrait",
    "storyboard-shot-list",
    "short-video-script",
    "manga-story-bible",
    "longform-to-short",
    "character-consistency",
    "dialogue-polish",
    "continuity-review",
)

_VISUAL_COMPILE: frozenset[str] = frozenset({
    "cinematic-still",
    "film-poster",
    "minimal-poster",
    "six-panel-comic",
    "lifestyle-portrait",
    "cinematic-triptych",
})


def primary_skill_key(keys: list[str] | None) -> str | None:
    """从已选 keys 里挑主 Skill，避免「竖屏短剧」路由的第一项 manga-story-bible 盖过成片链路。"""
    cleaned = [k for k in (keys or []) if k]
    if not cleaned:
        return None
    for key in _PRIMARY_PRIORITY:
        if key in cleaned:
            return key
    return cleaned[0]


def compile_profile_for(key: str | None) -> str:
    """执行编译形态：simple_visual / short_drama / text_chain / unknown。"""
    if not key:
        return "unknown"
    if key in _VISUAL_COMPILE:
        return "simple_visual"
    if key == "vertical-short-drama":
        return "short_drama"
    if key in SKILL_CATALOG:
        return "text_chain"
    return "unknown"


def trim_skeleton(
    skeleton: tuple[str, ...] | list[str],
    *,
    skip_labels: list[str] | None = None,
    stop_after: str | None = None,
    start_from: str | None = None,
) -> list[str]:
    """按用户指令裁剪骨架步骤（标签子串匹配）。"""
    steps = list(skeleton)
    skip = skip_labels or []
    if start_from:
        for i, label in enumerate(steps):
            if start_from in label:
                steps = steps[i:]
                break
    if stop_after:
        for i, label in enumerate(steps):
            if stop_after in label:
                steps = steps[: i + 1]
                break
    if skip:
        steps = [s for s in steps if not any(k in s for k in skip)]
    return steps
