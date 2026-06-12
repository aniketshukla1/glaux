"""Phase 5.2: HMAC request-signing auth (env-gated)."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from core import auth  # noqa: E402
from core.api import app  # noqa: E402

SECRET = "platform-secret-123"
client = TestClient(app)


# --- unit ----------------------------------------------------------------


def test_sign_verify_roundtrip():
    ts = str(int(time.time()))
    sig = auth.sign(SECRET, "POST", "/api/task", ts, b'{"directive":"x"}')
    assert auth.verify(SECRET, "POST", "/api/task", ts, b'{"directive":"x"}', sig)


def test_verify_rejects_tampered_body():
    ts = str(int(time.time()))
    sig = auth.sign(SECRET, "POST", "/api/task", ts, b'{"directive":"x"}')
    assert not auth.verify(SECRET, "POST", "/api/task", ts, b'{"directive":"HACKED"}', sig)


def test_verify_rejects_stale_timestamp():
    old = str(int(time.time()) - 10_000)
    sig = auth.sign(SECRET, "GET", "/api/health", old, b"")
    assert not auth.verify(SECRET, "GET", "/api/health", old, b"", sig)


def test_verify_rejects_wrong_secret():
    ts = str(int(time.time()))
    sig = auth.sign("other", "GET", "/api/ledger", ts, b"")
    assert not auth.verify(SECRET, "GET", "/api/ledger", ts, b"", sig)


# --- middleware enforcement ----------------------------------------------


def _headers(method, path, body=b""):
    ts = str(int(time.time()))
    return {auth.HEADER_TS: ts, auth.HEADER_SIG: auth.sign(SECRET, method, path, ts, body)}


def test_disabled_when_no_secret(monkeypatch):
    monkeypatch.delenv("ATHENA_API_SECRET", raising=False)
    assert client.get("/api/auth").json()["enabled"] is False
    # open: unsigned request works
    assert client.get("/api/ledger").status_code == 200


def test_enabled_rejects_unsigned(monkeypatch):
    monkeypatch.setenv("ATHENA_API_SECRET", SECRET)
    assert client.get("/api/auth").json()["enabled"] is True
    assert client.get("/api/ledger").status_code == 401
    # health + auth stay public so a client can bootstrap
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth").status_code == 200


def test_enabled_accepts_signed(monkeypatch):
    monkeypatch.setenv("ATHENA_API_SECRET", SECRET)
    assert client.get("/api/ledger", headers=_headers("GET", "/api/ledger")).status_code == 200
    body = b'{"directive":"signed dispatch"}'
    r = client.post(
        "/api/task",
        content=body,
        headers={"Content-Type": "application/json", **_headers("POST", "/api/task", body)},
    )
    assert r.status_code == 200


def test_enabled_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("ATHENA_API_SECRET", SECRET)
    r = client.get(
        "/api/ledger",
        headers={auth.HEADER_TS: str(int(time.time())), auth.HEADER_SIG: "deadbeef"},
    )
    assert r.status_code == 401
