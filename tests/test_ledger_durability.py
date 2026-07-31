"""Durable, independently-verifiable ledger + persistent agent identities."""

import json
import os

from fastapi.testclient import TestClient

from core.api import ROLES, _identities_path, _load_identities, _save_identities, app
from core.ledger import Ledger
from identity.keypair import AgentIdentity

client = TestClient(app)


def test_identities_persist_and_reload():
    idents = {role: AgentIdentity.generate() for role in ROLES}
    _save_identities(idents)
    # private keys are written 0600
    assert oct(os.stat(_identities_path()).st_mode)[-3:] == "600"
    loaded = _load_identities()
    assert loaded is not None
    for role in ROLES:
        assert loaded[role].public_key_b58 == idents[role].public_key_b58
        assert loaded[role].agent_id == idents[role].agent_id


def test_export_is_independently_verifiable(tmp_path):
    client.post("/api/task", json={"directive": "build a thing and summarize it"})
    ndjson = client.get("/api/ledger/export").text
    assert ndjson.strip(), "export should contain the signed chain"
    f = tmp_path / "athena-ledger.jsonl"
    f.write_text(ndjson)
    # the standalone verifier path: re-load + verify with no running server
    assert Ledger.load(str(f)).verify().valid


def test_export_tamper_is_detected(tmp_path):
    client.post("/api/task", json={"directive": "say hi"})
    lines = client.get("/api/ledger/export").text.strip().splitlines()
    assert lines
    bad = json.loads(lines[-1])
    bad["payload"] = json.dumps({"tampered": True})
    lines[-1] = json.dumps(bad)
    f = tmp_path / "tampered.jsonl"
    f.write_text("\n".join(lines) + "\n")
    assert not Ledger.load(str(f)).verify().valid


def test_export_is_byte_identical_to_the_kernel():
    """The export must be the kernel's own canonical bytes, not a re-serialization.

    Block hashes are computed over the serialized form, so round-tripping through
    Python's json (``json.dumps(ledger.block(i))``) can reformat a float timestamp
    into an equally-valid but different string and silently break the chain — an
    exported ledger that fails independent verification. That showed up only for
    certain timestamps, so this asserts the invariant directly instead of hoping
    a run produces an unlucky float.
    """
    from core.api import STATE

    client.post("/api/task", json={"directive": "summarize something briefly"})
    lines = client.get("/api/ledger/export").text.strip().splitlines()
    assert lines, "export should contain the signed chain"
    assert len(lines) == len(STATE.ledger)
    for i, line in enumerate(lines):
        assert line == STATE.ledger.block_json(i), f"block {i} was re-serialized on export"
