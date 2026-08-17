"""工作流轨道（纪律）：能不能发车、走哪步、参数合不合法。

模型只负责内容长相（prompt / 文案 / 创意取舍）；本模块禁止替模型写创意正文，
只回填与校验分辨率、时长、比例、模型兼容性等轨道参数。

比喻：工作流 = 铁路 + 信号；模型 = 火车头。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# —— 偏好默认（建节点时系统回填，不写死进 LLM prompt）——
VIDEO_PREF_MODEL = "agnes-video-v2.0"
VIDEO_PREF_RATIO = "16:9"
VIDEO_PREF_RESOLUTION = "1280x720"
VIDEO_PREF_DURATION = 5
VIDEO_PREF_GENERATE_AUDIO = True

IMAGE_PREF_MODEL = "agnes-image-2.1-flash"
IMAGE_PREF_RESOLUTION = "1920x1080"

# —— 模型能力（参数合法性；不在目录里编造）——
# duration 为闭区间秒；resolutions / ratios 为允许集合
VIDEO_CAPABILITIES: dict[str, dict[str, Any]] = {
    "agnes-video-v2.0": {
        "duration": (2, 18),
        "resolutions": {"1280x720", "720x1280", "1024x1024", "1920x1080", "1080x1920", "1152x768"},
        "ratios": {"16:9", "9:16", "1:1", "4:3", "3:4"},
        "display": "Agnes Video V2.0",
    },
    "seedance-1.0": {
        "duration": (2, 18),
        "resolutions": {"1280x720", "720x1280", "1024x1024", "1920x1080", "1080x1920"},
        "ratios": {"16:9", "9:16", "1:1", "4:3", "3:4"},
        "display": "Agnes Video V2.0",
    },
    "wan-2.1": {
        "duration": (2, 18),
        "resolutions": {"1280x720", "720x1280", "1024x1024", "1920x1080", "1080x1920"},
        "ratios": {"16:9", "9:16", "1:1", "4:3", "3:4"},
        "display": "Agnes Video V2.0",
    },
}

# 偏好模型不支持时，按此顺序找兼容模型（工作流换轨）
VIDEO_COMPAT_FALLBACK = (
    "agnes-video-v2.0",
)

_RATIO_TO_RES = {
    "16:9": "1280x720",
    "9:16": "720x1280",
    "1:1": "1024x1024",
}
_RES_TO_RATIO = {
    "1280x720": "16:9",
    "1920x1080": "16:9",
    "720x1280": "9:16",
    "1080x1920": "9:16",
    "1024x1024": "1:1",
}


@dataclass
class ParamResolveResult:
    """轨道参数解析结果；notes 供回复说明换模/纠偏原因。"""

    model: str
    params: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    switched: bool = False


def video_pref_defaults() -> dict[str, Any]:
    return {
        "model": VIDEO_PREF_MODEL,
        "ratio": VIDEO_PREF_RATIO,
        "resolution": VIDEO_PREF_RESOLUTION,
        "duration": VIDEO_PREF_DURATION,
        "generate_audio": VIDEO_PREF_GENERATE_AUDIO,
    }


def caps_for(model: str) -> dict[str, Any] | None:
    name = (model or "").strip()
    if name in VIDEO_CAPABILITIES:
        return VIDEO_CAPABILITIES[name]
    for key, caps in VIDEO_CAPABILITIES.items():
        if name.startswith(key) or key.startswith(name):
            return caps
    return None


def _supports(model: str, *, duration: int, resolution: str, ratio: str) -> bool:
    caps = caps_for(model)
    if not caps:
        # 未知模型：不做假能力断言，交给供应商；仅保证 duration 在全局安全窗
        return 2 <= int(duration) <= 18
    dmin, dmax = caps["duration"]
    if not (dmin <= int(duration) <= dmax):
        return False
    allowed_res = caps.get("resolutions") or set()
    allowed_ratio = caps.get("ratios") or set()
    if resolution and allowed_res and resolution not in allowed_res:
        return False
    if ratio and allowed_ratio and ratio not in allowed_ratio:
        return False
    return True


def find_compatible_video_model(
    *,
    preferred: str,
    duration: int,
    resolution: str,
    ratio: str,
) -> tuple[str, str | None]:
    """返回 (model, switch_reason)。preferred 可用则不换。"""
    pref = (preferred or VIDEO_PREF_MODEL).strip() or VIDEO_PREF_MODEL
    if _supports(pref, duration=duration, resolution=resolution, ratio=ratio):
        return pref, None
    pref_caps = caps_for(pref)
    pref_label = (pref_caps or {}).get("display") or pref
    for candidate in VIDEO_COMPAT_FALLBACK:
        if candidate == pref:
            continue
        if _supports(candidate, duration=duration, resolution=resolution, ratio=ratio):
            label = (caps_for(candidate) or {}).get("display") or candidate
            reason = (
                f"偏好模型 {pref_label} 不支持当前参数"
                f"（时长 {duration}s / {ratio or resolution}），已改用兼容模型 {label}"
            )
            return candidate, reason
    # 无兼容：钳到偏好模型能力上限，仍用偏好模型
    if pref_caps:
        dmin, dmax = pref_caps["duration"]
        clamped = max(dmin, min(int(duration), dmax))
        reason = (
            f"无兼容模型支持时长 {duration}s；已按 {pref_label} 能力钳到 {clamped}s"
        )
        return pref, reason
    return pref, f"无法校验模型能力，仍使用 {pref}"


def normalize_ratio_resolution(
    *,
    ratio: str | None,
    resolution: str | None,
) -> tuple[str, str]:
    r = (ratio or "").strip()
    res = (resolution or "").strip()
    if r and not res:
        res = _RATIO_TO_RES.get(r, VIDEO_PREF_RESOLUTION)
    elif res and not r:
        r = _RES_TO_RATIO.get(res, VIDEO_PREF_RATIO)
    elif not r and not res:
        r, res = VIDEO_PREF_RATIO, VIDEO_PREF_RESOLUTION
    elif r and res and _RES_TO_RATIO.get(res) != r:
        # 比例与分辨率冲突时以比例为准（用户改比例更常见）
        res = _RATIO_TO_RES.get(r, res)
    return r, res


def backfill_video_node_params(params: dict | None, *, user_content: str = "") -> dict[str, Any]:
    """建节点：用户显式 > 已有字段 > 偏好；不写 prompt。"""
    from .precedence import extract_user_explicit_params, merge_param_layers

    explicit = extract_user_explicit_params(user_content or "")
    # 调用方已写入的字段视为本轮规划结果（不低于偏好），但仍低于用户显式
    planned = dict(params or {})
    prefs = video_pref_defaults()
    merged = merge_param_layers(
        user_explicit=explicit,
        skill_workflow=planned,
        generation_pref={k: v for k, v in prefs.items() if k != "resolution"},
        model_default={},
        keys=("model", "ratio", "resolution", "duration", "generate_audio", "count"),
    )
    out = dict(planned)
    out.update(merged)

    import re

    m = str(out.get("model") or "").strip()
    user_named_model = bool(explicit.get("model")) or bool(
        re.search(r"agnes-video|agnes\s*video|seedance\s*2", user_content or "", re.I),
    )
    if not m:
        out["model"] = VIDEO_PREF_MODEL
    elif re.search(r"doubao-seedance|seedance", m, re.I) and not user_named_model:
        # 旧方舟模型名且用户未点名 → 拉回 Agnes 偏好
        out["model"] = VIDEO_PREF_MODEL
    ratio, resolution = normalize_ratio_resolution(
        ratio=str(out.get("ratio") or ""),
        resolution=str(out.get("resolution") or ""),
    )
    out["ratio"] = ratio
    out["resolution"] = resolution
    if "generate_audio" not in out or out.get("generate_audio") is None:
        out["generate_audio"] = VIDEO_PREF_GENERATE_AUDIO
    return out


def resolve_video_params(
    *,
    preferred_model: str | None = None,
    duration: int | None = None,
    ratio: str | None = None,
    resolution: str | None = None,
    generate_audio: bool | None = None,
    extra: dict | None = None,
    prompt: str = "",
    user_content: str = "",
    confirmed_action: dict | None = None,
) -> ParamResolveResult:
    """提交前：按优先级叠层 → 校验能力 → 不兼容则换轨并说明（禁止闷头覆盖）。"""
    from .precedence import extract_user_explicit_params, merge_param_layers

    prefs = video_pref_defaults()
    explicit = extract_user_explicit_params(user_content or "")
    confirmed = dict(confirmed_action or {})
    stacked = merge_param_layers(
        user_explicit=explicit,
        confirmed_action=confirmed,
        skill_workflow={
            "model": preferred_model,
            "duration": duration,
            "ratio": ratio,
            "resolution": resolution,
            "generate_audio": generate_audio,
        },
        generation_pref=prefs,
        keys=("model", "ratio", "resolution", "duration", "generate_audio"),
    )
    model = str(stacked.get("model") or prefs["model"]).strip() or prefs["model"]
    dur = int(stacked["duration"] if stacked.get("duration") is not None else prefs["duration"])
    ratio_n, res_n = normalize_ratio_resolution(
        ratio=str(stacked.get("ratio") or "") or None,
        resolution=str(stacked.get("resolution") or "") or None,
    )
    audio = bool(stacked["generate_audio"]) if stacked.get("generate_audio") is not None else prefs["generate_audio"]

    chosen, reason = find_compatible_video_model(
        preferred=model, duration=dur, resolution=res_n, ratio=ratio_n,
    )
    notes: list[str] = []
    switched = False
    if reason:
        # 用户显式点名的模型被换掉时，措辞强调「兼容方案」而非默默顶替
        if explicit.get("model") or confirmed.get("model"):
            notes.append(f"你指定的参数与模型能力冲突：{reason}")
        else:
            notes.append(reason)
        switched = chosen != model or "钳到" in reason
        # 若因无兼容而钳时长
        if "钳到" in reason and caps_for(chosen):
            dmin, dmax = caps_for(chosen)["duration"]
            dur = max(dmin, min(dur, dmax))

    # 换模后仍不支持则再钳一次
    caps = caps_for(chosen)
    if caps:
        dmin, dmax = caps["duration"]
        if not (dmin <= dur <= dmax):
            old = dur
            dur = max(dmin, min(dur, dmax))
            notes.append(f"时长 {old}s 超出 {(caps.get('display') or chosen)} 范围，已钳到 {dur}s")
        allowed_res = caps.get("resolutions") or set()
        if res_n and allowed_res and res_n not in allowed_res:
            # 按 ratio 回退到该模型可用分辨率
            for cand_res, cand_ratio in _RES_TO_RATIO.items():
                if cand_res in allowed_res and cand_ratio == ratio_n:
                    res_n = cand_res
                    notes.append(f"分辨率已对齐为 {res_n}（{ratio_n}）")
                    break

    params: dict[str, Any] = {
        "prompt": prompt,
        "count": 1,
        "duration": dur,
        "ratio": ratio_n,
        "resolution": res_n,
        "generate_audio": audio,
        "model": chosen,
        **(extra or {}),
    }
    # extra 不得冲掉已裁定的轨道字段（prompt 除外）
    params["duration"] = dur
    params["ratio"] = ratio_n
    params["resolution"] = res_n
    params["generate_audio"] = audio
    params["model"] = chosen
    if prompt:
        params["prompt"] = prompt

    return ParamResolveResult(model=chosen, params=params, notes=notes, switched=switched)


def action_route_hint(tool: str) -> str:
    """动作路由纪律：edit / exec / read。"""
    if tool.startswith(("get_", "list_", "search_", "check_")):
        return "read"
    if tool in {
        "submit_generation", "extract_frames", "trim_clip", "upscale",
        "compose_final", "capture_3d_scene",
    }:
        return "exec"
    if tool in {
        "create_nodes", "connect_nodes", "layout_nodes", "update_node_config",
        "delete_nodes", "change_model", "replace_output",
    }:
        return "edit"
    return "other"
