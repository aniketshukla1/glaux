"""Phase 0.1 exit criteria: identity, signing, tokens, and rotation."""

from __future__ import annotations

import time

import pytest

from identity import (
    AgentIdentity,
    CapabilityToken,
    KeyRegistry,
    canonical_bytes,
    issue_token,
    verify,
    verify_token,
)


# --- signing / verifying -------------------------------------------------


def test_sign_verify_roundtrip():
    agent = AgentIdentity.generate()
    payload = canonical_bytes({"msg": "hello swarm"})
    sig = agent.sign(payload)
    assert verify(agent.public_key_b58, payload, sig)


def test_tampered_payload_rejected():
    agent = AgentIdentity.generate()
    sig = agent.sign(canonical_bytes({"amount": 100}))
    tampered = canonical_bytes({"amount": 1_000_000})
    assert not verify(agent.public_key_b58, tampered, sig)


def test_wrong_key_rejected():
    a, b = AgentIdentity.generate(), AgentIdentity.generate()
    payload = canonical_bytes({"x": 1})
    sig = a.sign(payload)
    assert not verify(b.public_key_b58, payload, sig)


def test_agent_id_is_genesis_pubkey():
    agent = AgentIdentity.generate()
    assert agent.agent_id == agent.public_key_b58
    assert agent.namespace == "default"


def test_namespace_is_carried():
    agent = AgentIdentity.generate(namespace="acme")
    assert agent.namespace == "acme"


def test_verify_never_raises_on_garbage():
    assert not verify("not-a-key", b"x", "not-a-sig")


# --- persistence ---------------------------------------------------------


def test_save_load_roundtrip(tmp_path):
    agent = AgentIdentity.generate(namespace="acme")
    path = agent.save(tmp_path)
    assert oct(path.stat().st_mode)[-3:] == "600"

    loaded = AgentIdentity.load(agent.agent_id, tmp_path)
    assert loaded.agent_id == agent.agent_id
    assert loaded.namespace == "acme"
    # loaded key still produces verifiable signatures
    payload = canonical_bytes({"reloaded": True})
    assert verify(loaded.public_key_b58, payload, loaded.sign(payload))


# --- capability tokens ---------------------------------------------------


def test_token_issue_and_verify():
    issuer = AgentIdentity.generate()
    subject = AgentIdentity.generate()
    token = issue_token(issuer, subject.agent_id, "call_agent:researcher", ttl_seconds=60)
    assert verify_token(
        token,
        issuer.public_key_b58,
        subject=subject.agent_id,
        capability="call_agent:researcher",
    )


def test_token_expiry_rejected():
    issuer = AgentIdentity.generate()
    token = issue_token(issuer, "someone", "do_thing", ttl_seconds=-1)
    assert not verify_token(token, issuer.public_key_b58)


def test_token_subject_binding_enforced():
    issuer = AgentIdentity.generate()
    token = issue_token(issuer, "alice", "do_thing", ttl_seconds=60)
    assert not verify_token(token, issuer.public_key_b58, subject="mallory")


def test_token_tamper_rejected():
    issuer = AgentIdentity.generate()
    token = issue_token(issuer, "alice", "read", ttl_seconds=60)
    forged = CapabilityToken(
        issuer=token.issuer,
        subject=token.subject,
        capability="admin",  # escalated
        issued_at=token.issued_at,
        expires_at=token.expires_at,
        nonce=token.nonce,
        signature=token.signature,
    )
    assert not verify_token(forged, issuer.public_key_b58)


def test_token_wrong_issuer_key_rejected():
    issuer, other = AgentIdentity.generate(), AgentIdentity.generate()
    token = issue_token(issuer, "alice", "read", ttl_seconds=60)
    assert not verify_token(token, other.public_key_b58)


# --- key rotation --------------------------------------------------------


def test_rotation_changes_signing_key_not_id():
    agent = AgentIdentity.generate()
    genesis_pub = agent.public_key_b58
    agent.rotate()
    assert agent.agent_id == genesis_pub  # stable id
    assert agent.public_key_b58 != genesis_pub  # new signing key


def test_registry_resolves_key_by_time():
    agent = AgentIdentity.generate()
    genesis_pub = agent.public_key_b58

    reg = KeyRegistry()
    reg.register_genesis(agent.agent_id, genesis_pub, valid_from=0.0)

    # signature made by the genesis key at t0
    t0 = time.time()
    payload = canonical_bytes({"block": 1, "ts": t0})
    sig0 = agent.sign(payload)

    # rotate; registry applies it
    record = agent.rotate()
    assert reg.apply_rotation(record)
    new_pub = agent.public_key_b58

    # the genesis-era block still verifies against the key valid at t0
    key_then = reg.key_at(agent.agent_id, t0)
    assert key_then == genesis_pub
    assert verify(key_then, payload, sig0)

    # the current key is the new one; a fresh signature verifies against it
    assert reg.current_key(agent.agent_id) == new_pub
    fresh = canonical_bytes({"block": 2})
    assert verify(reg.key_at(agent.agent_id, time.time()), fresh, agent.sign(fresh))


def test_registry_rejects_unauthorized_rotation():
    agent = AgentIdentity.generate()
    attacker = AgentIdentity.generate()
    reg = KeyRegistry()
    reg.register_genesis(agent.agent_id, agent.public_key_b58)

    # forge a rotation record not signed by the current key
    forged = attacker.rotate()  # belongs to a different agent_id / key
    forged = type(forged)(
        agent_id=agent.agent_id,
        old_pubkey=agent.public_key_b58,
        new_pubkey=attacker.public_key_b58,
        rotated_at=time.time(),
        signature=forged.signature,  # signature by the wrong key
    )
    assert not reg.apply_rotation(forged)
    assert reg.current_key(agent.agent_id) == agent.public_key_b58


def test_verify_rotation_chain():
    agent = AgentIdentity.generate()
    genesis = agent.public_key_b58
    r1 = agent.rotate()
    r2 = agent.rotate()
    reg = KeyRegistry()
    assert reg.verify_rotation_chain(agent.agent_id, genesis, [r1, r2])
    # a broken chain (skip r1) must fail
    assert not reg.verify_rotation_chain(agent.agent_id, genesis, [r2])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
