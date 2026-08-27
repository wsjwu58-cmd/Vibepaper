"""带词维度的哈希嵌入：每个 token 映射到稳定维度，禁止无词频次数组余弦。"""

from __future__ import annotations

import hashlib
import math
import re

TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,2}|[a-zA-Z0-9]{2,}")
DEFAULT_DIM = 256


def hashed_embedding(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """token hashing trick：同一词落到同一维，符号由哈希决定。"""
    size = max(32, int(dim or DEFAULT_DIM))
    vec = [0.0] * size
    tokens = TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a[:n], b[:n]))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
