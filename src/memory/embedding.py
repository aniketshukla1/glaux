"""Embedding seam.

All text→vector conversion goes through the :class:`Embedder` interface so the
backend is swappable (OpenAI, sentence-transformers, a local model) without
touching the memory layer. Every embedder exposes a stable ``model_id`` that is
stamped onto each stored vector (the embedding-model invariant), so similarity
is never silently computed across incompatible embedding spaces.

The default :class:`HashingEmbedder` is deterministic and dependency-free —
no network, no torch — which keeps the entire memory system testable offline.
It is semantically weak but reproducible: identical text yields identical
vectors and shared tokens raise cosine similarity, which is enough to exercise
dedup, namespacing, and ranking.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Feature-hashing embedder. Deterministic and offline."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.model_id = f"hashing-v1-d{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN_RE.findall(text.lower()):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if (h[4] & 1) else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            inv = 1.0 / norm
            vec = [x * inv for x in vec]
        return vec
