"""Phase 3.4: cryptographic swarm ledger (native glaux_ledger core)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("glaux_ledger")

import glaux_ledger  # noqa: E402

from core.ledger import Action, GENESIS_HASH, Ledger  # noqa: E402
from identity import AgentIdentity, KeyRegistry, verify  # noqa: E402
from identity.canonical import canonical_bytes  # noqa: E402
from identity.keypair import RotationRecord  # noqa: E402


# --- native primitives / interop ----------------------------------------


def test_sha256_matches_known_vector():
    assert (
        glaux_ledger.sha256_hex(b"abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_native_signature_interoperates_with_python_identity():
    agent = AgentIdentity.generate()
    msg = b"cross-language message"
    sig = glaux_ledger.sign(agent.signing_key_b58(), msg)
    # signature produced in Rust verifies under Python `cryptography`
    assert verify(agent.public_key_b58, msg, sig)


# --- append / verify -----------------------------------------------------


def test_append_and_verify_clean_chain():
    led = Ledger()
    a = AgentIdentity.generate()
    led.append(a, Action.THINK, {"thought": "decompose the task"})
    led.append(a, Action.CALL_SKILL, {"skill_id": "sort", "args": [3, 1, 2]})
    led.append(a, Action.OBSERVATION, {"result": [1, 2, 3]})
    assert len(led) == 3
    assert led.blocks()[0]["prev_hash"] == GENESIS_HASH
    assert led.blocks()[1]["prev_hash"] == led.blocks()[0]["hash"]
    assert led.verify().valid


def test_multi_agent_chain_verifies():
    led = Ledger()
    router, coder = AgentIdentity.generate(), AgentIdentity.generate()
    led.append(router, Action.THINK, {"plan": ["code"]})
    led.append(router, Action.CALL_AGENT, {"to": coder.agent_id})
    led.append(coder, Action.CALL_SKILL, {"skill_id": "write_fn"})
    assert led.verify().valid
    assert led.blocks()[2]["agent_id"] == coder.agent_id


def test_payload_round_trips():
    led = Ledger()
    a = AgentIdentity.generate()
    led.append(a, Action.CALL_SKILL, {"skill_id": "y", "args": {"n": 5}})
    assert led.block(0)["payload"] == {"skill_id": "y", "args": {"n": 5}}


# --- tamper detection via the persisted ledger ---------------------------


def _rewrite_lines(path, mutate):
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    lines = mutate(lines)
    path.write_text("".join(json.dumps(b) + "\n" for b in lines))


def test_detects_payload_tampering(tmp_path):
    led = Ledger()
    a = AgentIdentity.generate()
    led.append(a, Action.CALL_SKILL, {"amount": 100})
    led.append(a, Action.OBSERVATION, {"ok": True})
    path = tmp_path / "l.jsonl"
    led.save(path)

    def mutate(blocks):
        blocks[0]["payload"] = {"amount": 1_000_000}  # tamper, leave hash/sig
        return blocks

    _rewrite_lines(path, mutate)
    result = Ledger.load(path).verify()
    assert not result.valid
    assert result.first_bad_index == 0
    assert "hash" in result.reason


def test_detects_signature_tampering(tmp_path):
    led = Ledger()
    a = AgentIdentity.generate()
    led.append(a, Action.THINK, {"x": 1})
    path = tmp_path / "l.jsonl"
    led.save(path)

    other = AgentIdentity.generate()

    def mutate(blocks):
        # syntactically valid signature, but over the wrong content/key
        blocks[0]["signature"] = glaux_ledger.sign(other.signing_key_b58(), b"wrong")
        return blocks

    _rewrite_lines(path, mutate)
    result = Ledger.load(path).verify()
    assert not result.valid
    assert result.first_bad_index == 0
    assert "signature" in result.reason


def test_detects_removed_block(tmp_path):
    led = Ledger()
    a = AgentIdentity.generate()
    for i in range(3):
        led.append(a, Action.THINK, {"i": i})
    path = tmp_path / "l.jsonl"
    led.save(path)

    def mutate(blocks):
        del blocks[1]  # excise a block -> index/link no longer line up
        return blocks

    _rewrite_lines(path, mutate)
    result = Ledger.load(path).verify()
    assert not result.valid
    assert result.first_bad_index == 1


# --- rotation-aware verification -----------------------------------------


def test_rotation_aware_verify_positive():
    led = Ledger()
    agent = AgentIdentity.generate()
    reg = KeyRegistry()
    reg.register_genesis(agent.agent_id, agent.public_key_b58, valid_from=0.0)

    led.append(agent, Action.THINK, {"era": "genesis"}, timestamp=100.0)
    record = agent.rotate()
    assert reg.apply_rotation(record)
    led.append(agent, Action.THINK, {"era": "post"}, timestamp=record.rotated_at + 10)

    assert led.verify(registry=reg).valid


def test_rotation_aware_verify_rejects_key_outside_window():
    led = Ledger()
    agent = AgentIdentity.generate()
    genesis_pub = agent.public_key_b58

    # two blocks signed by the genesis key, at t=100 and t=200
    led.append(agent, Action.THINK, {"n": 1}, timestamp=100.0)
    led.append(agent, Action.THINK, {"n": 2}, timestamp=200.0)

    # registry: genesis valid only until t=150 (rotation authorized by genesis key)
    reg = KeyRegistry()
    reg.register_genesis(agent.agent_id, genesis_pub, valid_from=0.0)
    new_id = AgentIdentity.generate()
    unsigned = {
        "agent_id": agent.agent_id,
        "old_pubkey": genesis_pub,
        "new_pubkey": new_id.public_key_b58,
        "rotated_at": 150.0,
    }
    sig = agent.sign(canonical_bytes(unsigned))  # genesis key still current here
    reg.apply_rotation(
        RotationRecord(agent.agent_id, genesis_pub, new_id.public_key_b58, 150.0, sig)
    )

    # block at t=200 used the genesis key, but the registry says it expired at 150
    result = led.verify(registry=reg)
    assert not result.valid
    assert result.first_bad_index == 1


# --- persistence & scale -------------------------------------------------


def test_save_load_roundtrip(tmp_path):
    led = Ledger()
    a = AgentIdentity.generate()
    led.append(a, Action.THINK, {"x": 1})
    led.append(a, Action.CALL_SKILL, {"skill_id": "y"})
    path = tmp_path / "ledger.jsonl"
    led.save(path)

    reloaded = Ledger.load(path)
    assert len(reloaded) == 2
    assert reloaded.verify().valid
    assert reloaded.block(1)["payload"] == {"skill_id": "y"}


def test_large_chain_verifies():
    led = Ledger()
    a = AgentIdentity.generate()
    for i in range(2000):
        led.append(a, Action.THINK, {"i": i})
    assert led.verify().valid
