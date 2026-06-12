"""Platform API auth — HMAC request signing.

The dashboard (and any client) authenticates with a shared platform secret that
is *separate* from the agents' Ed25519 keypairs: agent identity proves "which
agent did this" on the ledger; this proves "this caller may use the API".

Each request carries an `X-Athena-Timestamp` and an `X-Athena-Signature` =
HMAC-SHA256(secret, "{ts}\\n{METHOD}\\n{path}\\n{sha256(body)}"). The server
re-derives it, constant-time compares, and rejects stale timestamps (replay
window). Auth is enforced only when `ATHENA_API_SECRET` is set — otherwise the
API is open (convenient for local/offline dev).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

HEADER_TS = "x-athena-timestamp"
HEADER_SIG = "x-athena-signature"
WINDOW_SECONDS = 300


def current_secret() -> Optional[str]:
    return os.environ.get("ATHENA_API_SECRET") or None


def _canonical(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode("utf-8")


def sign(secret: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), _canonical(method, path, timestamp, body), hashlib.sha256
    ).hexdigest()


def verify(
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    signature: str,
    *,
    now: Optional[float] = None,
    window: int = WINDOW_SECONDS,
) -> bool:
    now = now if now is not None else time.time()
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(now - ts) > window:
        return False
    expected = sign(secret, method, path, timestamp, body)
    return hmac.compare_digest(expected, signature or "")
