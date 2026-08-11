"""视频任务参数：时长与预估点数随任务/模型解析，禁止硬编码。"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import httpx

from ..core.config import settings

_DURATION_MIN = 2
_DURATION_MAX = 12

# 明确指「单段视频时长」的表述（避免把「30秒短剧」总量误当 clip 时长）
_CLIP_DURATION = re.compile(
    r"(?:生成|做成|转为|转成|输出|做)\s*(\d+)\s*秒(?:的)?(?:视频|短片|动画|片段)?|"
    r"(\d+)\s*秒(?:的)?(?:视频|短片|动画|片段)|"
    r"(\d+)\s*s(?:ec)?(?:\s*video)?|"
    r"时长\s*[:：]?\s*(\d+)\s*秒|"
    r"每(?:镜|段|个镜头)\s*(\d+)\s*秒",
    re.I,
)
_TOTAL_SECONDS = re.compile(r"(\d+)\s*秒(?:短剧|广告|故事|视频)?", re.I)
_HALF_MINUTE = re.compile(r"半分钟|30秒左右", re.I)
_ONE_MINUTE = re.compile(r"一分钟|60秒", re.I)


@lru_cache(maxsize=8)
def _catalog(model_type: str = "video") -> tuple[dict[str, dict], dict[str, dict]]:
    """返回 (by_name, by_type_first) 模型目录快照。"""
    try:
        r = httpx.get(
            f"{settings.generation_base_url}/api/v1/models",
            params={"type": model_type},
            timeout=8,
            trust_env=False,
        )
        if r.status_code != 200:
            return {}, {}
        items = r.json().get("items") or []
        by_name = {str(m.get("name")): m for m in items if m.get("name")}
        first = items[0] if items else {}
        return by_name, {model_type: first}
    except Exception:
        return {}, {}


def get_video_model(name: str | None = None) -> dict:
    by_name, by_type = _catalog("video")
    if name and name in by_name:
        return by_name[name]
    if name:
        for key, m in by_name.items():
            if key.startswith(name) or name in key:
                return m
    return by_type.get("video") or {}


def _clamp_duration(seconds: int) -> int:
    return max(_DURATION_MIN, min(int(seconds), _DURATION_MAX))


def parse_clip_duration_from_text(content: str) -> int | None:
    """从文案解析单段 clip 时长；无法确定时返回 None。"""
    text = (content or "").strip()
    if not text:
        return None
    m = _CLIP_DURATION.search(text)
    if m:
        raw = next(g for g in m.groups() if g)
        return _clamp_duration(int(raw))
    if _HALF_MINUTE.search(text):
        return _clamp_duration(30)
    if _ONE_MINUTE.search(text):
        return _clamp_duration(60)
    return None


def parse_total_seconds_from_text(content: str) -> int | None:
    m = _TOTAL_SECONDS.search(content or "")
    return int(m.group(1)) if m else None


def duration_from_nodes(nodes: list[dict] | None) -> int | None:
    for n in nodes or []:
        params = n.get("params") or {}
        if not isinstance(params, dict):
            continue
        raw = params.get("duration") or params.get("durationSeconds") or params.get("clipDuration")
        if raw is not None:
            try:
                return _clamp_duration(int(raw))
            except (TypeError, ValueError):
                continue
    return None


def resolve_video_duration(
    *,
    content: str = "",
    model_name: str | None = None,
    selected_nodes: list[dict] | None = None,
    node_params: dict | None = None,
    shot_count: int | None = None,
) -> int:
    """按优先级解析视频时长：总量均分 → 文案 clip → 节点参数 → 模型默认。"""
    total = parse_total_seconds_from_text(content)
    if total is not None and shot_count and shot_count > 0:
        if re.search(r"短剧|广告|故事|镜头", content or "", re.I):
            return _clamp_duration(max(1, total // shot_count))

    from_text = parse_clip_duration_from_text(content)
    if from_text is not None:
        return from_text

    from_selected = duration_from_nodes(selected_nodes)
    if from_selected is not None:
        return from_selected

    if node_params:
        raw = node_params.get("duration") or node_params.get("durationSeconds")
        if raw is not None:
            try:
                return _clamp_duration(int(raw))
            except (TypeError, ValueError):
                pass

    model = get_video_model(model_name)
    defaults = model.get("defaultParams") or {}
    raw = defaults.get("duration")
    if raw is not None:
        try:
            return _clamp_duration(int(raw))
        except (TypeError, ValueError):
            pass

    # 模型目录未给出时与 generation-service provider 下限一致
    return _clamp_duration(5)


# Agent / 节点默认视频模型：Seedance 1.0 Pro（勿默默升到 1.5 / 2.0）
DEFAULT_VIDEO_MODEL = "doubao-seedance-1-0-pro-250528"


def resolve_video_model_name(preferred: str | None = None) -> str:
    """解析视频模型名；无显式指定时固定 Seedance 1.0 Pro。"""
    if preferred:
        model = get_video_model(preferred)
        name = str(model.get("name") or preferred).strip()
        if name:
            return name
    model = get_video_model(DEFAULT_VIDEO_MODEL)
    return str(model.get("name") or DEFAULT_VIDEO_MODEL)


def estimate_video_cost(model_name: str, model_params: dict) -> int:
    """按 generation-service 模型目录/估价接口计算点数。"""
    params = dict(model_params or {})
    try:
        r = httpx.post(
            f"{settings.generation_base_url}/api/v1/models/estimate",
            json={"modelType": "video", "modelParams": params, "count": int(params.get("count") or 1)},
            timeout=8,
            trust_env=False,
        )
        if r.status_code == 200:
            data = r.json()
            for m in data.get("models") or []:
                if m.get("name") == model_name:
                    return max(1, int(m.get("estimatedCost") or 1))
            if data.get("estimatedCost") is not None:
                return max(1, int(data["estimatedCost"]))
    except Exception:
        pass
    model = get_video_model(model_name)
    return max(1, int(model.get("basePrice") or 30))


def build_video_task_params(
    *,
    content: str,
    prompt: str,
    model_name: str | None = None,
    canvas: dict | None = None,
    selected_ids: list[int] | None = None,
    shot_count: int | None = None,
    extra: dict | None = None,
    node_params: dict | None = None,
) -> dict[str, Any]:
    """统一构造视频节点/提交任务参数。"""
    nodes = (canvas or {}).get("nodes") or []
    ids = set(int(x) for x in (selected_ids or []))
    selected_nodes = [n for n in nodes if n.get("id") in ids] if ids else []

    model = resolve_video_model_name(model_name)
    duration = resolve_video_duration(
        content=content,
        model_name=model,
        selected_nodes=selected_nodes,
        node_params=node_params,
        shot_count=shot_count,
    )
    model_params = {"prompt": prompt, "count": 1, "duration": duration, **(extra or {})}
    model_info = get_video_model(model)
    defaults = model_info.get("defaultParams") or {}
    if defaults.get("resolution") and "resolution" not in model_params:
        model_params["resolution"] = defaults["resolution"]

    return {
        "model": model,
        "duration": duration,
        "model_params": model_params,
        "estimated_cost": estimate_video_cost(model, model_params),
    }


def video_submit_from_node(node: dict, *, content: str = "", shot_count: int | None = None) -> dict:
    """从已规划的视频节点生成 submit_generation 参数。"""
    params = node.get("params") or {}
    prompt = str(node.get("prompt") or params.get("prompt") or "")
    task = build_video_task_params(
        content=content,
        prompt=prompt,
        model_name=params.get("model"),
        node_params=params,
        shot_count=shot_count,
    )
    return {
        "model_type": "video",
        "model_params": task["model_params"],
        "estimated_cost": task["estimated_cost"],
    }
