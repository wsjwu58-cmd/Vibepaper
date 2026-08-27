"""角色 schema → 白名单 TOOLS。LLM 不得输出裸 node_id 或直接工具参数。"""

from __future__ import annotations

from typing import Any

from .drama_schema import (
    AudioCue,
    CharacterLook,
    ContinuityConstraint,
    ProducerDecision,
    Scene,
    SeriesBible,
    ShotSpec,
    SubtitleCue,
)


def _node(type_: str, creative: str, title: str, prompt: str, x: float, y: float, extra: dict | None = None) -> dict:
    params = {"title": title, "prompt": prompt, "ratio": "9:16", **(extra or {})}
    return {
        "type": type_,
        "creativeType": creative,
        "x": x,
        "y": y,
        "params": params,
        "prompt": prompt,
    }


def compile_series_bible(bible: SeriesBible, theme: str) -> list[dict[str, Any]]:
    prompt = (
        f"【故事圣经 v{bible.canon_version}】\n前提：{bible.premise}\n"
        f"世界观：{'；'.join(bible.world_rules)}\n风格边界：{bible.style_boundary}\n"
        f"用户题材：{theme}"
    )
    return [{
        "tool_name": "create_nodes",
        "params": {"nodes": [_node("text", "script", "故事圣经", prompt, 80, 80)]},
        "summary": "创建故事圣经节点",
        "step_id": "bible",
    }]


def compile_screenwriter(scenes: list[Scene], theme: str) -> list[dict[str, Any]]:
    body = "\n".join(
        f"场{s.scene_order} {s.goal} | {s.setting} | 钩子：{s.hook}\n对白：{' / '.join(s.dialogue)}"
        for s in scenes
    )
    prompt = f"【分场剧本】{theme}\n{body}"
    return [{
        "tool_name": "create_nodes",
        "params": {"nodes": [_node("text", "shot", "分场剧本", prompt, 80, 220)]},
        "summary": "创建分场剧本",
        "step_id": "episode_script",
    }]


def compile_looks(looks: list[CharacterLook]) -> list[dict[str, Any]]:
    nodes = []
    for i, look in enumerate(looks):
        prompt = (
            f"角色外观 v{look.version}：服装 {look.costume}；发型 {look.hair}。"
            "生成正面肖像作为后续镜头 reference，禁止改脸。"
        )
        nodes.append(_node("image", "character", f"角色外观 v{look.version}", prompt, 80, 360 + i * 140, {
            "characterId": look.character_id,
            "lookVersion": look.version,
            "referenceAssetIds": look.reference_asset_ids,
        }))
    if not nodes:
        return []
    return [{
        "tool_name": "create_nodes",
        "params": {"nodes": nodes},
        "summary": "创建角色外观参考图",
        "step_id": "character_look",
    }]


def compile_shotspecs(shots: list[ShotSpec], constraints: list[ContinuityConstraint] | None = None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    image_nodes = []
    video_nodes = []
    audio_nodes = []
    subtitle_nodes = []
    for i, shot in enumerate(shots):
        continuity = constraints or [c.model_dump() for c in shot.continuity]
        kf_prompt = (
            f"镜头{shot.shot_no} 首帧。目的：{shot.purpose}。机位：{shot.camera}。"
            f"屏幕方向：{shot.screen_direction}。场景：{shot.setting}。光线：{shot.lighting}。"
            f"比例 {shot.ratio}。"
        )
        clip_prompt = (
            f"镜头{shot.shot_no} 视频 {shot.duration}s。运镜：{shot.camera}。"
            f"对白：{shot.dialogue}。接续：{shot.join_method}。"
        )
        image_nodes.append(_node("image", "keyframe", f"镜头{shot.shot_no}首帧", kf_prompt, 380, 80 + i * 160, {
            "shotNo": shot.shot_no,
            "shotSpecId": shot.id,
            "duration": shot.duration,
            "ratio": shot.ratio,
            "continuity": continuity,
        }))
        video_nodes.append(_node("video", "clip", f"镜头{shot.shot_no}视频", clip_prompt, 680, 80 + i * 160, {
            "shotNo": shot.shot_no,
            "shotSpecId": shot.id,
            "duration": shot.duration,
            "ratio": shot.ratio,
        }))
        if shot.dialogue or shot.audio_cues:
            audio_nodes.append(_node("audio", "audio", f"镜头{shot.shot_no}音轨", shot.dialogue or "音效/BGM", 980, 80 + i * 160, {
                "shotNo": shot.shot_no,
                "audioCues": shot.audio_cues,
            }))
            subtitle_nodes.append(_node("text", "shot", f"镜头{shot.shot_no}字幕", shot.dialogue, 980, 80 + i * 160 + 70, {
                "shotNo": shot.shot_no,
                "kind": "subtitle",
            }))
    if image_nodes:
        actions.append({
            "tool_name": "create_nodes",
            "params": {"nodes": image_nodes},
            "summary": f"创建 {len(image_nodes)} 个镜头首帧",
            "step_id": "keyframes",
        })
    if video_nodes:
        actions.append({
            "tool_name": "create_nodes",
            "params": {"nodes": video_nodes},
            "summary": f"创建 {len(video_nodes)} 个镜头视频",
            "step_id": "clips",
        })
    if audio_nodes:
        actions.append({
            "tool_name": "create_nodes",
            "params": {"nodes": audio_nodes + subtitle_nodes},
            "summary": "创建音轨与字幕节点",
            "step_id": "audio_subtitle",
        })
    n_shot = len(shots)
    edges = []
    # $created 下标由执行器解析；adapter 只描述相对别名
    for i in range(n_shot):
        edges.append({
            "sourceNodeId": f"$created[{i}]",
            "targetNodeId": f"$created[{n_shot + i}]",
            "dependencyType": "input",
        })
    if edges:
        actions.append({
            "tool_name": "connect_nodes",
            "params": {"edges": edges},
            "summary": "首帧接入对应镜头视频",
            "step_id": "shot_edges",
        })
    return actions


def compile_timeline(shot_count: int) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": "create_nodes",
            "params": {"nodes": [_node("compose", "composite", "成片时间线", "按镜头序混音、字幕、转场后合成", 1280, 200)]},
            "summary": "创建时间线合成节点",
            "step_id": "timeline",
        },
        {
            "tool_name": "compose_final",
            "params": {"estimated_cost": 15},
            "summary": "提交时间线合成",
            "step_id": "compose",
        },
    ]


def compile_producer(decision: ProducerDecision) -> list[dict[str, Any]]:
    if decision.action == "abort":
        return []
    if decision.action == "human_review":
        return []
    if decision.action == "rerun_local":
        return [{
            "tool_name": "submit_generation",
            "params": {"estimated_cost": int(decision.estimated_cost or 8), "rerun": True},
            "summary": "局部重跑失败镜头",
            "step_id": "rerun",
        }]
    return [{
        "tool_name": "submit_generation",
        "params": {"estimated_cost": int(decision.estimated_cost or 8)},
        "summary": "按制片决定提交生成",
        "step_id": "producer_submit",
    }]


def compile_audio_cues(cues: list[AudioCue], subs: list[SubtitleCue]) -> dict[str, Any]:
    return {
        "audio": [c.model_dump() for c in cues],
        "subtitles": [s.model_dump() for s in subs],
    }
