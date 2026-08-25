"""取舍优先级：用户显式 > confirmedAction > Skill/工作流 > 生成偏好 > 模型默认。

越靠前越不可被覆盖；越靠后只做「缺了才补」。
工作流是默认剧本，用户指令是导演改动——冲突时导演优先，但必须说明后果。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal, Mapping

Stance = Literal["discuss", "instruct"]

# 轨道参数：允许按层回填 / 覆盖的键（创意正文 prompt 不在此列）
TRACK_KEYS = frozenset({
    "model", "modelRef", "model_name", "modelName",
    "ratio", "resolution", "duration", "generate_audio", "generateAudio",
    "count", "size",
})

PRECEDENCE_ORDER = (
    "platform_constraint",
    "confirmed_action",
    "user_explicit",
    "project_constraint",
    "skill_workflow",
    "generation_pref",
    "model_default",
)

_DISCUSS = re.compile(
    r"(要不要|好不好|怎么样|如何选|如何办|是否|能不能|可不可以|"
    r"有没有必要|该不该|还是|或者|建议一下|怎么看|你觉得|"
    r"哪[个种]好|哪种更好)",
    re.I,
)
_QUESTION_TAIL = re.compile(r"[？?]\s*$|吗\s*[？?]?\s*$|呢\s*[？?]?\s*$")

_STRONG_INSTRUCT = re.compile(
    r"(生成|提交|创建|新建|删除|移除|覆盖|重跑|重做|换成|改成|改为|"
    r"设为|设置为|做成|转为|转成|添加到画布|开始执行|继续推进|"
    r"用侧光|用顶光|用逆光)",
    re.I,
)
_SOFT_INSTRUCT = re.compile(
    r"^(用|改|做|写|画|删|加|接|连|排|推进|确认)\S",
    re.I,
)

_RATIO = re.compile(r"(16\s*[:：]\s*9|9\s*[:：]\s*16|1\s*[:：]\s*1)", re.I)
_RES = re.compile(r"(3840\s*[x×]\s*2160|1920\s*[x×]\s*1080|1280\s*[x×]\s*720|"
                  r"1080\s*[x×]\s*1920|720\s*[x×]\s*1280|1024\s*[x×]\s*1024)", re.I)
_MODEL_HINT = re.compile(
    r"(agnes[\-\s]?video[\w\.\-]*|agnes[\-\s]?image[\w\.\-]*|"
    r"seedance\s*2\.0|seedance\s*2|seedance\s*1\.5|seedance\s*1\.0|"
    r"doubao-seedance[\w\-]*|seedream\s*5|seedream\s*4|"
    r"doubao-seedream[\w\-]*|deepseek[\w\-]*|可灵|kling)",
    re.I,
)

_READ_PREFIXES = ("get_", "list_", "search_", "check_", "load_")
_WRITE_TOOLS = frozenset({
    "create_nodes", "connect_nodes", "layout_nodes", "update_node_config",
    "delete_nodes", "change_model", "replace_output", "submit_generation",
    "extract_frames", "trim_clip", "upscale", "outpaint", "compose_final", "capture_3d_scene",
    "update_memory", "clock",
})

_EXEC_INTENTS = frozenset({
    "create", "generate", "delete", "update", "connect", "layout", "model",
    "search", "advance_pipeline", "reregenerate_stale", "orchestrate_workflow",
    "outpaint", "upscale", "extract_frames", "trim_clip",
})

_PAPER_READ = frozenset({"summarize", "copy", "directions"})


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def fill_missing(
    base: Mapping[str, Any] | None,
    fill: Mapping[str, Any] | None,
    *,
    keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """缺了才补，不缺不塞。"""
    out = dict(base or {})
    allow = set(keys) if keys is not None else None
    for key, val in (fill or {}).items():
        if allow is not None and key not in allow:
            continue
        if is_empty(val):
            continue
        if key not in out or is_empty(out.get(key)):
            out[key] = val
    return out


def merge_param_layers(
    *,
    user_explicit: Mapping[str, Any] | None = None,
    confirmed_action: Mapping[str, Any] | None = None,
    skill_workflow: Mapping[str, Any] | None = None,
    generation_pref: Mapping[str, Any] | None = None,
    model_default: Mapping[str, Any] | None = None,
    project_constraint: Mapping[str, Any] | None = None,
    keys: Iterable[str] | None = TRACK_KEYS,
) -> dict[str, Any]:
    """自低向高叠层：高层非空覆盖低层。

    优先级：model_default < pref < skill < project < user_explicit < confirmed_action
    """
    allow = set(keys) if keys is not None else None
    out: dict[str, Any] = {}
    for layer in (
        model_default,
        generation_pref,
        skill_workflow,
        project_constraint,
        user_explicit,
        confirmed_action,
    ):
        if not layer:
            continue
        for key, val in layer.items():
            if allow is not None and key not in allow:
                continue
            if is_empty(val):
                continue
            out[key] = val
    return out


def apply_confirmed_action(
    planned_params: Mapping[str, Any] | None,
    confirmed: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """确认卡上手改配置冻结为最终输入；覆盖 planned，但保留内部元数据键。"""
    out = dict(planned_params or {})
    if not confirmed:
        return out
    reserved = {
        "estimated_cost", "estimatedCost", "chain_estimated_cost", "chainEstimatedCost",
        "node_id", "nodeId", "node_ids", "canvas_id", "canvasId",
    }
    for key, val in confirmed.items():
        if key in reserved:
            continue
        if is_empty(val):
            continue
        out[key] = val
    return out


def classify_stance(content: str, intent: str | None = None) -> Stance:
    """分辨讨论 vs 下指令。

    讨论：解释规则、给建议，不擅自执行。
    下指令：执行；规则只做约束与风险短评。
    """
    text = (content or "").strip()
    if not text:
        return "discuss"

    intent_l = (intent or "").strip().lower()
    if intent_l in _PAPER_READ and not re.search(r"添加到画布|写入画布|创建节点", text, re.I):
        return "discuss"

    discuss_hit = bool(_DISCUSS.search(text) or _QUESTION_TAIL.search(text))
    strong = bool(_STRONG_INSTRUCT.search(text))

    # 「要不要用侧光」类：讨论标记压过弱执行词
    if discuss_hit and not re.search(
        r"(直接|立刻|马上|现在就).{0,6}(生成|创建|删除|提交)|添加到画布",
        text,
        re.I,
    ):
        # 仍允许极强命令句压过问句壳
        if strong and re.search(r"(请|帮我).{0,8}(生成|创建|删除|提交)", text, re.I):
            return "instruct"
        return "discuss"

    if strong or intent_l in _EXEC_INTENTS:
        return "instruct"

    if len(text) <= 48 and _SOFT_INSTRUCT.search(text) and not discuss_hit:
        return "instruct"

    return "discuss" if discuss_hit else "instruct"


def extract_user_explicit_params(content: str) -> dict[str, Any]:
    """从用户原文抽取显式轨道参数（只抽说死的，不猜）。"""
    text = content or ""
    out: dict[str, Any] = {}

    from .video_task import parse_clip_duration_from_text

    dur = parse_clip_duration_from_text(text)
    if dur is not None:
        out["duration"] = dur

    rm = _RATIO.search(text)
    if rm:
        raw = re.sub(r"\s+", "", rm.group(1)).replace("：", ":")
        out["ratio"] = raw

    res_m = _RES.search(text)
    if res_m:
        out["resolution"] = re.sub(r"[×xX]", "x", re.sub(r"\s+", "", res_m.group(1)))

    mm = _MODEL_HINT.search(text)
    if mm:
        hint = re.sub(r"\s+", "", mm.group(1)).lower()
        if "agnes" in hint and "image" in hint:
            out["model"] = "agnes-image-2.1-flash"
        elif "agnes" in hint and "video" in hint:
            out["model"] = "agnes-video-v2.0"
        elif "agnes" in hint:
            out["model"] = "agnes-video-v2.0"
        elif "2.0" in hint or "seedance2" in hint.replace("-", "").replace(".", ""):
            out["model"] = "agnes-video-v2.0"
        elif "1.5" in hint or "1-5" in hint or "1.0" in hint or "1-0" in hint:
            out["model"] = "agnes-video-v2.0"
        elif hint.startswith("doubao-seedance") or hint.startswith("doubao-seedream"):
            out["model"] = "agnes-video-v2.0" if "seedance" in hint or "seedream" not in hint else "agnes-image-2.1-flash"
            if "seedream" in hint:
                out["model"] = "agnes-image-2.1-flash"
        elif hint.startswith("deepseek") or "agnes-2.5" in hint or hint in {"agnes-flash", "agnes-text"}:
            out["model"] = "agnes-2.5-flash"
        elif "seedream5" in hint.replace(".", "").replace("-", "") or "seedream" in hint:
            out["model"] = "agnes-image-2.1-flash"
        elif "kling" in hint or "可灵" in hint:
            out["model"] = "agnes-video-v2.0"

    if re.search(r"(不要|关闭|关掉|无).{0,4}(音轨|音频|声音)|mute|no\s*audio", text, re.I):
        out["generate_audio"] = False
    elif re.search(r"(带|开启|打开|要).{0,4}(音轨|音频|声音)|with\s*audio", text, re.I):
        out["generate_audio"] = True

    return out


def filter_actions_for_stance(
    actions: Iterable[Any],
    stance: Stance,
) -> list[Any]:
    """讨论态：去掉写/执行类动作，只保留只读查询。"""
    items = list(actions or [])
    if stance != "discuss":
        return items

    kept: list[Any] = []
    for a in items:
        if isinstance(a, dict):
            tool = str(a.get("tool_name") or a.get("tool") or "")
        else:
            tool = str(getattr(a, "tool_name", "") or "")
        if tool.startswith(_READ_PREFIXES):
            kept.append(a)
            continue
        if tool in _WRITE_TOOLS:
            continue
        # 未知工具：讨论态默认不执行
    return kept


def precedence_prompt_block() -> str:
    """注入 LLM system 的优先级契约短文。"""
    return (
        "取舍优先级（高→低，不可倒置）："
        "平台硬约束/工具能力 > 确认卡 confirmedAction > 用户本轮显式指令 > 项目约束 > "
        "Skill/工作流补位 > 生成偏好 > 模型默认。\n"
        "- 先分辨讨论 vs 下指令：讨论只给判断/方案，不擅自 create/submit；"
        "下指令则执行，规则只做合法性约束与一句风险点破。\n"
        "- 用户点名的模型/分辨率/时长/比例必须写入参数，禁止用偏好覆盖；"
        "未点名才回填偏好，偏好也没有才用模型 defaults（缺了才补）。\n"
        "- Skill/工作流只补用户没说清的结构（角色一致、分镜拆分），"
        "不得反过来要求用户按默认剧本改方向。\n"
        "- 冲突时用户优先，但若参数不合法（如模型不支持该时长），"
        "必须说明原因并查兼容模型/给替代方案，禁止默默顶掉也不解释。"
    )
