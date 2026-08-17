"""从 LLM 文本中稳健提取 JSON 对象/数组。"""

from __future__ import annotations

import json
import re
from typing import Any


def _strip_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json|JSON)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _extract_balanced(text: str, open_ch: str = "{", close_ch: str = "}") -> str | None:
    start = text.find(open_ch)
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _light_repair(blob: str) -> str:
    s = blob.strip()
    # 中文引号 → 英文
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # 尾逗号
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # 单行末尾多余逗号后再接 }
    return s


def parse_llm_json(raw: str, *, expect: type = dict) -> Any:
    """解析模型输出的 JSON；容忍 markdown 围栏、尾逗号、多余前后缀。

    Raises:
        json.JSONDecodeError / ValueError: 无法修复时抛出。
    """
    text = _strip_fences(raw or "")
    candidates: list[str] = []
    if text:
        candidates.append(text)
    obj = _extract_balanced(text, "{", "}")
    if obj:
        candidates.append(obj)
    arr = _extract_balanced(text, "[", "]")
    if arr and expect is list:
        candidates.append(arr)
    # greedy fallback（旧逻辑）
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        candidates.append(m.group(0))
    if expect is list:
        m2 = re.search(r"\[.*\]", text, re.S)
        if m2:
            candidates.append(m2.group(0))

    last_err: Exception | None = None
    seen: set[str] = set()
    for cand in candidates:
        for variant in (cand, _light_repair(cand)):
            if not variant or variant in seen:
                continue
            seen.add(variant)
            try:
                data = json.loads(variant)
            except Exception as exc:  # noqa: BLE001 — 继续尝试下一候选
                last_err = exc
                continue
            if expect is dict and isinstance(data, dict):
                return data
            if expect is list and isinstance(data, list):
                return data
            if expect is dict and isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
            last_err = ValueError(f"JSON type mismatch: {type(data).__name__}")
    if last_err:
        raise last_err
    raise ValueError("empty LLM JSON")
