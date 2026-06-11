"""Phase 4: skill synthesis, static cap-check, and library lifecycle."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athenadb")

import safety  # noqa: E402
from llm import ScriptedLLM  # noqa: E402
from memory import MemoryManager  # noqa: E402
from skills import (  # noqa: E402
    DEPRECATED,
    PROMOTED,
    QUARANTINED,
    SkillLibrary,
    SkillSynthesizer,
    static_cap_check,
)


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _skill_json(name="reverse_string", code="def run(s):\n    return s[::-1]\n", caps=None, tests=None):
    obj = {
        "name": name,
        "description": "test skill",
        "entrypoint": "run",
        "caps": caps or {"time_limit_s": 5},
        "code": code,
        "tests": tests if tests is not None else ['assert run("abc") == "cba"'],
    }
    return "```json\n" + json.dumps(obj) + "\n```"


# --- static cap check ----------------------------------------------------


def test_capcheck_flags_network_without_cap():
    v = static_cap_check("import socket\ndef run():\n    return socket.socket()\n", {"net": False})
    assert any("network" in x for x in v)


def test_capcheck_allows_network_with_cap():
    assert static_cap_check("import socket\n", {"net": True}) == []


def test_capcheck_blocks_subprocess_always():
    v = static_cap_check("import subprocess\n", {"net": True, "fs_write": ["/"]})
    assert any("subprocess" in x for x in v)


def test_capcheck_flags_file_write_without_fs_write():
    v = static_cap_check("def run():\n    open('/tmp/x', 'w')\n", {})
    assert any("fs_write" in x for x in v)


def test_capcheck_clean_pure_function():
    assert static_cap_check("def run(s):\n    return s[::-1]\n", {}) == []


# --- synthesizer ---------------------------------------------------------


def test_synthesize_passing_skill():
    synth = SkillSynthesizer(ScriptedLLM([_skill_json()]))
    res = synth.synthesize("reverse a string")
    assert res.ok
    assert res.tests_passed
    assert res.candidate.name == "reverse_string"


def test_synthesize_rejects_failing_tests():
    bad = _skill_json(code="def run(s):\n    return s\n", tests=['assert run("abc") == "cba"'])
    res = SkillSynthesizer(ScriptedLLM([bad])).synthesize("reverse a string")
    assert not res.ok
    assert not res.tests_passed
    assert res.test_results[0]["ok"] is False


def test_synthesize_rejects_cap_violation():
    sneaky = _skill_json(
        code="import socket\ndef run(s):\n    return s[::-1]\n",
        caps={"net": False, "time_limit_s": 5},
    )
    res = SkillSynthesizer(ScriptedLLM([sneaky])).synthesize("reverse a string")
    assert not res.ok
    assert res.cap_violations  # rejected before running tests


# --- library lifecycle ---------------------------------------------------


def test_add_candidate_quarantines(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural)
    synth = SkillSynthesizer(ScriptedLLM([_skill_json()]))
    rec = lib.add_candidate(synth.synthesize("reverse").candidate)
    assert rec.status == QUARANTINED
    assert lib.get(rec.id).name == "reverse_string"


def test_promote_after_successes(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural, promote_after=3)
    rec = lib.add_candidate(SkillSynthesizer(ScriptedLLM([_skill_json()])).synthesize("x").candidate)
    for _ in range(2):
        r = lib.record_use(rec.id, success=True)
        assert r.status == QUARANTINED
    r = lib.record_use(rec.id, success=True)  # 3rd success
    assert r.status == PROMOTED
    assert r.success_rate == 1.0


def test_deprecate_on_low_success(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural, min_uses_for_deprecation=3, deprecate_below=0.5)
    rec = lib.add_candidate(SkillSynthesizer(ScriptedLLM([_skill_json()])).synthesize("x").candidate)
    lib.record_use(rec.id, success=False)
    lib.record_use(rec.id, success=False)
    r = lib.record_use(rec.id, success=True)  # 1/3 = 0.33 < 0.5
    assert r.status == DEPRECATED


def test_versioning_links_near_duplicate(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural, version_threshold=0.9)
    s = SkillSynthesizer(ScriptedLLM([_skill_json(), _skill_json()]))
    first = lib.add_candidate(s.synthesize("reverse").candidate)
    second = lib.add_candidate(s.synthesize("reverse").candidate)  # identical name+desc
    assert second.version == 2
    assert second.parent_skill_id == first.id
    assert len(lib.list()) == 2  # versioned, not merged


def test_list_filters_by_status(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural, promote_after=1)
    rec = lib.add_candidate(SkillSynthesizer(ScriptedLLM([_skill_json()])).synthesize("x").candidate)
    lib.record_use(rec.id, success=True)  # -> promoted
    assert len(lib.list(status=PROMOTED)) == 1
    assert lib.list(status=QUARANTINED) == []
