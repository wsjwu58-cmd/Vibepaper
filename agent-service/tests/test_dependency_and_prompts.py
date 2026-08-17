"""prompt_builder 与 dependency_scheduler 单元测试。"""

from agent.domain.dependency_scheduler import (
    all_inputs_ready,
    find_submittable_nodes,
    is_node_ready,
    is_node_submittable,
    plan_downstream_submits,
)
from agent.domain.prompt_builder import (
    build_node_prompt,
    extract_theme,
    extract_visual_goal,
    prompt_for_media_create,
)
from agent.domain.workflow_orchestrator import plan_short_drama_workflow
from agent.agent.planner import plan


def test_extract_theme_strips_commands():
    theme = extract_theme("帮我做一个30秒短剧，主角是黑猫")
    assert "帮我" not in theme
    assert "黑猫" in theme


def test_extract_theme_keeps_subject_after_workflow_word():
    """「按照工作流生成橘猫和恶狼的短剧」不得被切成空壳。"""
    theme = extract_theme("按照工作流生成橘猫和恶狼的短剧")
    assert "橘猫" in theme and "恶狼" in theme
    assert "工作流" not in theme


def test_extract_visual_goal_keeps_subject():
    """「生成黑猫视频」必须留下「黑猫」，不能被媒介词整段抹掉。"""
    assert "黑猫" in extract_visual_goal("生成黑猫视频")
    assert "视频" not in extract_visual_goal("生成黑猫视频")
    assert "赛博朋克" in extract_visual_goal("画一张赛博朋克风格的城市夜景海报")


def test_per_node_prompts_use_theme_not_shell():
    """不再注入「请直接写出…」空模板壳；方向来自用户主题。"""
    user = "做一个30秒短剧，3个镜头，主角是穿铠甲的狼"
    script = build_node_prompt(role="script", user_theme=user)
    shot = build_node_prompt(role="shot", user_theme=user, shot_count=3)
    kf = build_node_prompt(role="keyframe", user_theme=user, shot_index=1, shot_count=3)
    clip = build_node_prompt(role="clip", user_theme=user, shot_index=1, shot_count=3)
    assert "请直接写出" not in script
    assert "请直接写出" not in shot
    assert "铠甲" in script or "狼" in script
    assert "拆成" in shot or "镜" in shot
    assert "镜头" in kf
    assert "运镜" in clip or "推近" in clip or "跟拍" in clip or "微动" in clip


def test_prompt_philosophy_no_empty_shell():
    """用户定方向；空模板壳已下线。"""
    user = "按照工作流生成橘猫和恶狼的短剧"
    script = build_node_prompt(role="script", user_theme=user)
    clip = build_node_prompt(role="clip", user_theme=user, shot_index=2, shot_count=3)
    assert "橘猫" in script and "恶狼" in script
    assert "请直接写出" not in script
    assert not script.startswith("【总脚本】")
    assert ("运镜" in clip) or ("推近" in clip) or ("微动" in clip) or ("首帧" in clip)


def test_prompt_for_media_create_keeps_subject():
    user = "画一张赛博朋克风格的城市夜景海报"
    prompt = prompt_for_media_create(user, "image", "keyframe")
    assert "请直接写出" not in prompt
    assert len(prompt) >= 8
    assert "赛博朋克" in prompt or "城市" in prompt


def test_prompt_for_black_cat_video_includes_subject():
    """单点「生成黑猫视频」不能落成空壳「镜头1/基于首帧」。"""
    prompt = prompt_for_media_create("生成黑猫视频", "video")
    assert "黑猫" in prompt
    assert "基于首帧" not in prompt
    assert "镜头1" not in prompt
    actions = plan("生成黑猫视频", {"nodes": [], "edges": []}, [])
    create = next(a for a in actions if a.tool_name == "create_nodes")
    node = create.params["nodes"][0]
    node_prompt = node.get("prompt") or (node.get("params") or {}).get("prompt")
    assert "黑猫" in node_prompt
    assert "基于首帧" not in node_prompt


def test_short_drama_submits_only_root_node():
    result = plan_short_drama_workflow("做一个30秒短剧，3个镜头", None)
    submits = [a for a in result.actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["node_id"] == "$created[0]"
    assert submits[0].params["model_type"] == "text"
    creates = [a for a in result.actions if a.tool_name == "create_nodes"]
    assert len(creates) >= 3


def test_short_drama_node_prompts_unique():
    result = plan_short_drama_workflow("做一个30秒短剧，3个镜头，主角是黑猫", None)
    prompts = []
    for action in result.actions:
        if action.tool_name != "create_nodes":
            continue
        for node in action.params.get("nodes") or []:
            p = node.get("prompt") or (node.get("params") or {}).get("prompt")
            if p:
                prompts.append(p)
    assert len(prompts) >= 5
    assert len(set(prompts)) == len(prompts)


def test_dependency_ready_detection():
    nodes = [
        {"id": 1, "type": "text", "creativeType": "script", "execStatus": "ready"},
        {"id": 2, "type": "text", "creativeType": "shot", "execStatus": "idle"},
        {"id": 3, "type": "image", "creativeType": "keyframe", "execStatus": "idle"},
    ]
    edges = [
        {"source": 1, "target": 2, "dependencyType": "input"},
        {"source": 2, "target": 3, "dependencyType": "input"},
    ]
    ctx = {"nodes": nodes, "edges": edges}
    assert is_node_ready(nodes[0])
    assert not is_node_submittable(nodes[0])
    ready = find_submittable_nodes(ctx)
    assert len(ready) == 1
    assert ready[0]["id"] == 2

    nodes[1]["execStatus"] = "ready"
    ready2 = find_submittable_nodes(ctx, prefer_downstream_of=2)
    assert any(n["id"] == 3 for n in ready2)


def test_all_inputs_ready():
    nodes = [
        {"id": 1, "execStatus": "ready"},
        {"id": 2, "execStatus": "idle"},
    ]
    edges = [{"source": 1, "target": 2, "dependencyType": "input"}]
    assert all_inputs_ready(2, nodes, edges)
    nodes[0]["execStatus"] = "running"
    assert not all_inputs_ready(2, nodes, edges)


def test_plan_downstream_after_script():
    nodes = [
        {"id": 1, "type": "text", "creativeType": "script", "execStatus": "ready",
         "prompt": "脚本内容", "params": {"title": "总脚本", "prompt": "脚本"}},
        {"id": 2, "type": "text", "creativeType": "shot", "execStatus": "idle",
         "prompt": "分镜表", "params": {"title": "分镜清单", "prompt": "分镜表"}},
    ]
    edges = [{"source": 1, "target": 2, "dependencyType": "input"}]
    actions = plan_downstream_submits({"nodes": nodes, "edges": edges}, completed_node_id=1)
    assert len(actions) == 1
    assert actions[0].tool_name == "submit_generation"
    assert actions[0].params["node_id"] == 2


def test_plan_downstream_does_not_fallback_to_unrelated_nodes():
    """完成节点没有直接下游时，不得把画布上所有 idle 节点都提交一遍。"""
    nodes = [
        {"id": 1, "type": "text", "creativeType": "script", "execStatus": "ready"},
        {"id": 9, "type": "image", "creativeType": "keyframe", "execStatus": "idle"},
        {"id": 10, "type": "image", "creativeType": "keyframe", "execStatus": "stale"},
    ]
    edges = []
    actions = plan_downstream_submits({"nodes": nodes, "edges": edges}, completed_node_id=1)
    assert actions == []


def test_image_then_video_pipeline_prompts_and_deps():
    from agent.agent.planner import plan, _is_image_then_video

    msg = "先生成图片，然后根据图片生成视频，主角是穿铠甲的狼"
    assert _is_image_then_video(msg)
    actions = plan(msg, {"nodes": [], "edges": []}, [])
    creates = next(a for a in actions if a.tool_name == "create_nodes")
    nodes = creates.params["nodes"]
    assert len(nodes) == 2
    assert nodes[0]["type"] == "image"
    assert nodes[1]["type"] == "video"
    assert nodes[0].get("prompt")
    assert nodes[1].get("prompt")
    assert msg not in nodes[0]["prompt"]
    assert msg not in nodes[1]["prompt"]
    submits = [a for a in actions if a.tool_name == "submit_generation"]
    assert len(submits) == 1
    assert submits[0].params["model_type"] == "image"


def test_image_to_video_waits_for_upstream():
    from agent.agent.planner import plan

    actions = plan(
        "根据当前黑黄猫打架图片生成2秒视频",
        {"nodes": [{"id": 101, "type": "image", "execStatus": "running"}], "edges": []},
        [101],
    )
    submits = [a for a in actions if a.tool_name == "submit_generation"]
    assert len(submits) == 0


def test_default_video_model_is_pref_model():
    from agent.domain.video_task import DEFAULT_VIDEO_MODEL, resolve_video_model_name
    from agent.domain.workflow_rails import VIDEO_PREF_MODEL

    assert DEFAULT_VIDEO_MODEL == VIDEO_PREF_MODEL
    assert resolve_video_model_name(None) == VIDEO_PREF_MODEL or VIDEO_PREF_MODEL in resolve_video_model_name(None)
