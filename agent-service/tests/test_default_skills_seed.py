"""默认 Skill 种子：只入库，运行时不读 md。"""

from agent.domain.default_skills_seed import DEFAULT_SKILLS_SEED


def test_default_skills_seed_has_sixteen():
    assert len(DEFAULT_SKILLS_SEED) == 16
    names = {s["name"] for s in DEFAULT_SKILLS_SEED}
    assert "AI角色一致性控制" in names
    assert "六格漫画" in names
    assert "分镜与镜头清单" in names
    assert "竖屏短剧单集生成" in names
    assert "Canvas Cookbook" in names
    for s in DEFAULT_SKILLS_SEED:
        assert s["description"]
        assert s["instructions"]
        assert s["category"] in ("image", "video", "text", "canvas", "general")
