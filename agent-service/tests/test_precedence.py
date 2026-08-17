"""取舍优先级：用户显式 > confirmedAction > Skill > 偏好 > 模型默认。"""

from agent.domain.precedence import (
    apply_confirmed_action,
    classify_stance,
    extract_user_explicit_params,
    fill_missing,
    filter_actions_for_stance,
    merge_param_layers,
)
from agent.domain.workflow_rails import VIDEO_PREF_MODEL, backfill_video_node_params, resolve_video_params


def test_discuss_vs_instruct():
    assert classify_stance("这个镜头要不要用侧光") == "discuss"
    assert classify_stance("侧光好不好") == "discuss"
    assert classify_stance("用侧光") == "instruct"
    assert classify_stance("生成一段 8 秒视频") == "instruct"
    assert classify_stance("梳理一下画布", "summarize") == "discuss"


def test_merge_user_explicit_beats_pref():
    out = merge_param_layers(
        user_explicit={"duration": 8, "ratio": "9:16"},
        generation_pref={"duration": 4, "ratio": "16:9", "model": VIDEO_PREF_MODEL},
        model_default={"duration": 5},
    )
    assert out["duration"] == 8
    assert out["ratio"] == "9:16"
    assert out["model"] == VIDEO_PREF_MODEL


def test_confirmed_action_beats_skill_and_pref():
    out = merge_param_layers(
        confirmed_action={"duration": 3, "model": "agnes-video-v2.0"},
        skill_workflow={"duration": 8, "model": VIDEO_PREF_MODEL},
        generation_pref={"duration": 4, "model": VIDEO_PREF_MODEL},
    )
    assert out["duration"] == 3
    assert out["model"] == "agnes-video-v2.0"


def test_fill_missing_does_not_overwrite():
    assert fill_missing({"duration": 8}, {"duration": 4, "ratio": "16:9"}) == {
        "duration": 8,
        "ratio": "16:9",
    }


def test_apply_confirmed_action_freezes_user_edits():
    merged = apply_confirmed_action(
        {"duration": 4, "ratio": "16:9", "estimated_cost": 35, "node_id": 1},
        {"duration": 8, "ratio": "9:16", "estimated_cost": 999},
    )
    assert merged["duration"] == 8
    assert merged["ratio"] == "9:16"
    # 内部元数据不被确认卡覆盖
    assert merged["estimated_cost"] == 35
    assert merged["node_id"] == 1


def test_discuss_filters_write_actions():
    actions = [
        {"tool_name": "get_canvas_summary", "params": {}},
        {"tool_name": "create_nodes", "params": {"nodes": []}},
        {"tool_name": "submit_generation", "params": {}},
    ]
    kept = filter_actions_for_stance(actions, "discuss")
    assert [a["tool_name"] for a in kept] == ["get_canvas_summary"]
    assert filter_actions_for_stance(actions, "instruct") == actions


def test_extract_and_backfill_respect_user_ratio():
    explicit = extract_user_explicit_params("用 9:16 竖屏，做 8 秒视频")
    assert explicit["ratio"] == "9:16"
    assert explicit["duration"] == 8
    out = backfill_video_node_params({}, user_content="用 9:16 竖屏，做 8 秒视频")
    assert out["ratio"] == "9:16"
    assert out["resolution"] == "720x1280"
    assert out["duration"] == 8


def test_skill_invented_legacy_seedance_pulled_back_without_user_name():
    out = backfill_video_node_params(
        {"model": "doubao-seedance-2-0-260128"},
        user_content="生成一段城市夜景视频",
    )
    assert out["model"] == VIDEO_PREF_MODEL


def test_user_named_agnes_or_legacy_maps_to_agnes():
    out = backfill_video_node_params(
        {},
        user_content="用 Agnes Video 生成城市夜景",
    )
    assert out["model"] == VIDEO_PREF_MODEL
    legacy = backfill_video_node_params(
        {},
        user_content="用 Seedance 2.0 生成城市夜景",
    )
    assert legacy["model"] == VIDEO_PREF_MODEL


def test_conflict_notes_when_duration_exceeds_capability():
    result = resolve_video_params(
        preferred_model=VIDEO_PREF_MODEL,
        duration=25,
        ratio="16:9",
    )
    assert result.params["duration"] == 18
    assert result.notes
    assert any("冲突" in n or "兼容" in n or "不支持" in n or "钳到" in n for n in result.notes)
