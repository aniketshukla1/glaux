"""Canonical byte serialization for signing.

Every signature in Athena is computed over the canonical bytes of a JSON
object. Canonical = deterministic key ordering and no insignificant
whitespace, so the same logical payload always produces identical bytes
regardless of dict insertion order or platform.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_bytes(obj: Any) -> bytes:
    """Serialize ``obj`` to deterministic UTF-8 bytes for signing/verifying."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
