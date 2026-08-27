"""短剧领域 schema：角色步骤只输出这些合同，不得直接吐 node_id。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SeriesBible(BaseModel):
    id: str | None = None
    premise: str
    world_rules: list[str] = Field(default_factory=list)
    canon_version: int = 1
    style_boundary: str = ""
    content_boundary: str = ""
    default_ratio: str = "9:16"
    budget_cap: int | None = None


class Episode(BaseModel):
    id: str | None = None
    series_id: str | None = None
    episode_no: int
    goal: str
    hook: str = ""
    title: str = ""
    duration_seconds: int | None = None


class Scene(BaseModel):
    id: str | None = None
    episode_id: str | None = None
    scene_order: int
    goal: str
    setting: str = ""
    conflict: str = ""
    dialogue: list[str] = Field(default_factory=list)
    hook: str = ""


class CharacterProfile(BaseModel):
    id: str | None = None
    series_id: str | None = None
    name: str
    identity_anchor: str
    static_traits: list[str] = Field(default_factory=list)
    dynamic_state: dict[str, Any] = Field(default_factory=dict)


class CharacterLook(BaseModel):
    id: str | None = None
    character_id: str
    version: int = 1
    costume: str = ""
    hair: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)
    three_view_asset_ids: list[str] = Field(default_factory=list)


class ContinuityConstraint(BaseModel):
    id: str | None = None
    subject: str
    rule: str
    scope: Literal["shot", "scene", "episode"] = "scene"
    severity: Literal["must", "should", "optional"] = "must"
    mutable_in_shot: bool = False


class ShotSpec(BaseModel):
    id: str | None = None
    scene_id: str | None = None
    shot_no: int
    duration: float = 2.0
    purpose: str
    camera: str = ""
    screen_direction: str = ""
    dialogue: str = ""
    audio_cues: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    look_versions: dict[str, int] = Field(default_factory=dict)
    props: list[str] = Field(default_factory=list)
    setting: str = ""
    lighting: str = ""
    mood: str = ""
    previous_ending_state: str = ""
    join_method: str = "cut"
    immutable_fields: list[str] = Field(default_factory=list)
    continuity: list[ContinuityConstraint] = Field(default_factory=list)
    ratio: str = "9:16"


class AudioCue(BaseModel):
    id: str | None = None
    shot_id: str | None = None
    kind: Literal["dialogue", "narration", "sfx", "bgm"] = "dialogue"
    text: str = ""
    voice: str = ""
    start_ms: int = 0
    duration_ms: int = 0


class SubtitleCue(BaseModel):
    id: str | None = None
    shot_id: str | None = None
    text: str
    start_ms: int = 0
    end_ms: int = 0
    language: str = "zh-CN"


class RenderReview(BaseModel):
    id: str | None = None
    target_node_id: str
    target_kind: Literal["keyframe", "clip", "episode"] = "clip"
    scores: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    recommended_action: Literal["accept", "rerun_local", "human_review", "abort"] = "accept"
    evidence: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0


class ScreenwriterOutput(BaseModel):
    episode: Episode
    scenes: list[Scene]


class StoryboardOutput(BaseModel):
    shots: list[ShotSpec]


class ContinuityOutput(BaseModel):
    looks: list[CharacterLook]
    constraints: list[ContinuityConstraint]


class SoundDesignOutput(BaseModel):
    audio: list[AudioCue]
    subtitles: list[SubtitleCue]


class ProducerDecision(BaseModel):
    action: Literal["submit", "rerun_local", "human_review", "abort"]
    reason: str = ""
    shot_ids: list[str] = Field(default_factory=list)
    estimated_cost: int = 0
