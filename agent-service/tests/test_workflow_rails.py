"""工作流轨道：偏好回填 + 参数合法性 + 兼容换模。"""

from agent.domain.workflow_rails import (
    VIDEO_PREF_DURATION,
    VIDEO_PREF_MODEL,
    VIDEO_PREF_RESOLUTION,
    backfill_video_node_params,
    resolve_video_params,
)
from agent.domain.video_task import build_video_task_params, parse_clip_duration_from_text


def test_backfill_applies_video_prefs():
    out = backfill_video_node_params({})
    assert out["model"] == VIDEO_PREF_MODEL
    assert out["duration"] == VIDEO_PREF_DURATION
    assert out["resolution"] == VIDEO_PREF_RESOLUTION
    assert out["ratio"] == "16:9"
    assert out["generate_audio"] is True


def test_backfill_does_not_overwrite_explicit():
    out = backfill_video_node_params({"duration": 3, "ratio": "9:16"})
    assert out["duration"] == 3
    assert out["ratio"] == "9:16"
    assert out["resolution"] == "720x1280"


def test_eight_seconds_stays_on_agnes():
    """Agnes Video 支持约 18s；8s 应留在偏好模型。"""
    result = resolve_video_params(
        preferred_model=VIDEO_PREF_MODEL,
        duration=8,
        ratio="16:9",
        resolution="1280x720",
        prompt="缓慢推近",
    )
    assert result.model == VIDEO_PREF_MODEL
    assert result.params["duration"] == 8


def test_build_video_task_clamps_over_max():
    task = build_video_task_params(
        content="我要 25 秒视频",
        prompt="月光下缓慢横移",
        model_name=VIDEO_PREF_MODEL,
    )
    assert parse_clip_duration_from_text("我要 25 秒视频") == 18
    assert task["duration"] == 18
    assert task["model"] == VIDEO_PREF_MODEL

    result = resolve_video_params(
        preferred_model=VIDEO_PREF_MODEL,
        duration=25,
        ratio="16:9",
        resolution="1280x720",
        prompt="月光下缓慢横移",
    )
    assert result.params["duration"] == 18
    assert result.notes
    assert any("钳到" in n or "不支持" in n for n in result.notes)


def test_persona_states_rail_vs_locomotive():
    from agent.agent.persona import AGENT_PERSONA, PAPER_AGENT_INSTRUCTIONS

    assert "铁路" in AGENT_PERSONA or "工作流（纪律）" in AGENT_PERSONA
    assert "兼容方案" in PAPER_AGENT_INSTRUCTIONS or "兼容" in PAPER_AGENT_INSTRUCTIONS
