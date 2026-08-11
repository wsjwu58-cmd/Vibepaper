"""modality → 具体模型解析。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from generation.services.model_resolve import resolve_model_config


def test_resolve_exact_name():
    db = MagicMock()
    model = SimpleNamespace(name="deepseek-v4-pro", model_type="text", provider="deepseek", enabled=True)
    db.query.return_value.filter.return_value.first.return_value = model
    assert resolve_model_config(db, "deepseek-v4-pro") is model


def test_resolve_text_alias_prefers_llm_model():
    db = MagicMock()
    preferred = SimpleNamespace(
        name="deepseek-v4-pro", model_type="text", provider="deepseek", enabled=True,
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
