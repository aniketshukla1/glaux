"""User accounts: password hashing, signed tokens, and the user store."""

from __future__ import annotations

import time

import pytest

from core import users


def test_password_hash_roundtrip_and_uniqueness():
    h1 = users.hash_password("correct horse")
    h2 = users.hash_password("correct horse")
    assert h1 != h2  # salted
    assert users.verify_password("correct horse", h1)
    assert not users.verify_password("wrong", h1)
    assert not users.verify_password("correct horse", "not-a-hash")


def test_token_sign_verify_and_tamper():
    secret = "s3cret"
    tok = users.issue_token(secret, "u1", 0)
    payload = users.verify_token(secret, tok)
    assert payload and payload["uid"] == "u1" and payload["ver"] == 0
    assert users.verify_token("other-secret", tok) is None  # wrong key
    assert users.verify_token(secret, tok + "x") is None     # tampered
    assert users.verify_token(secret, "garbage") is None


def test_token_expiry():
    secret = "s"
    tok = users.issue_token(secret, "u1", 0, ttl=-1)
    assert users.verify_token(secret, tok) is None


def test_store_create_authenticate_and_persist(tmp_path):
    path = tmp_path / "users.json"
    store = users.UserStore(path)
    u = store.create("Ada@example.com", "password123", name="Ada")
    assert u.name == "Ada" and u.email == "Ada@example.com"
    assert "password123" not in path.read_text()  # never stored in the clear
    assert store.authenticate("ada@example.com", "password123").id == u.id  # case-insensitive
    assert store.authenticate("ada@example.com", "nope") is None
    # reload from disk
    assert users.UserStore(path).by_email("ada@example.com").id == u.id


def test_store_rejects_bad_input_and_duplicates(tmp_path):
    store = users.UserStore(tmp_path / "u.json")
    with pytest.raises(users.UserError):
        store.create("not-an-email", "password123")
    with pytest.raises(users.UserError):
        store.create("a@b.com", "short")
    store.create("a@b.com", "password123")
    with pytest.raises(users.UserError):
        store.create("A@B.com", "password123")  # duplicate (case-insensitive)


def test_change_password_invalidates_tokens(tmp_path):
    store = users.UserStore(tmp_path / "u.json")
    u = store.create("a@b.com", "password123")
    assert u.token_version == 0
    with pytest.raises(users.UserError):
        store.change_password(u, "wrong", "newpassword1")
    store.change_password(u, "password123", "newpassword1")
    assert u.token_version == 1 and store.authenticate("a@b.com", "newpassword1")


def test_update_profile_and_settings(tmp_path):
    store = users.UserStore(tmp_path / "u.json")
    u = store.create("a@b.com", "password123", name="A")
    store.update_profile(u, name="Ada", settings={"theme": "oled"})
    store.update_profile(u, settings={"default_model": "qwen"})
    assert u.name == "Ada"
    assert u.settings == {"theme": "oled", "default_model": "qwen"}  # merged, not replaced
    assert "password_hash" not in u.public()
