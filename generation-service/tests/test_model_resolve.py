"""modality → 具体模型解析。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from generation.services.model_resolve import resolve_model_config


def test_resolve_exact_name():
    db = MagicMock()
    model = SimpleNamespace(name="agnes-2.5-flash", model_type="text", provider="agnes-text", enabled=True)
    db.query.return_value.filter.return_value.first.return_value = model
    assert resolve_model_config(db, "agnes-2.5-flash") is model


def test_resolve_legacy_text_alias():
    db = MagicMock()
    model = SimpleNamespace(name="agnes-2.5-flash", model_type="text", provider="agnes-text", enabled=True)
    db.query.return_value.filter.return_value.first.return_value = model
    assert resolve_model_config(db, "deepseek-v4-pro") is model


def test_resolve_text_alias_prefers_llm_model():
    db = MagicMock()
    preferred = SimpleNamespace(
        name="agnes-2.5-flash", model_type="text", provider="agnes-text", enabled=True,
    )

    # first().first() for exact miss, then preferred hit
    q = MagicMock()
    db.query.return_value = q

    # Call chain varies; stub filter().first / filter().order_by().all
    def _filter(*_a, **_k):
        return q

    q.filter.side_effect = _filter
    # exact miss, then preferred hit
    q.first.side_effect = [None, preferred]
    q.order_by.return_value.all.return_value = []

    got = resolve_model_config(db, "text")
    assert got is preferred


def test_agnes_text_provider_not_image():
    from generation.providers.providers import get_provider

    assert get_provider("agnes-text", "text").name == "openai-text"
    assert get_provider("agnes-2.5-flash", "text").name == "openai-text"
    assert get_provider("agnes-text", "agnes-2.5-flash").name == "openai-text"
    assert get_provider("agnes-image", "image").name == "agnes-image"
