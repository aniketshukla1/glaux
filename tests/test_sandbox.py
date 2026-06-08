"""Phase 0.2: skill sandbox isolation and resource limits."""

from __future__ import annotations

import pytest

import safety
from sandbox import Capabilities, run


@pytest.fixture(autouse=True)
def _live_mode():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


# --- basic execution -----------------------------------------------------


def test_simple_return_value():
    res = run(
        "def main(x):\n    return x * 2\n",
        caps=Capabilities(time_limit_s=5),
        inputs={"x": 21},
        entrypoint="main",
    )
    assert res.ok
    assert res.return_value == 42


def test_stdout_captured():
    res = run("print('hello from skill')", caps=Capabilities(time_limit_s=5))
    assert res.ok
    assert "hello from skill" in res.stdout


def test_skill_exception_reported():
    res = run("raise ValueError('boom')", caps=Capabilities(time_limit_s=5))
    assert not res.ok
    assert "ValueError: boom" in res.error
    assert "ValueError" in (res.traceback or "")


def test_missing_entrypoint_errors():
    res = run("x = 1", caps=Capabilities(time_limit_s=5), entrypoint="nope")
    assert not res.ok
    assert "nope" in res.error


# --- resource limits -----------------------------------------------------


def test_infinite_loop_killed_by_timeout():
    res = run("while True:\n    pass\n", caps=Capabilities(time_limit_s=1))
    assert not res.ok
    assert res.killed_reason == "timeout"
    assert res.duration_s < 5  # killed promptly, not hung


def test_memory_bomb_killed():
    code = (
        "import time\n"
        "chunks = []\n"
        "for _ in range(10000):\n"
        "    chunks.append(bytearray(8 * 1024 * 1024))\n"
        "    time.sleep(0.01)\n"
    )
    res = run(code, caps=Capabilities(time_limit_s=20, mem_mb=128))
    assert not res.ok
    assert res.killed_reason == "memory"


# --- network guard -------------------------------------------------------


def test_network_blocked_by_default():
    res = run(
        "import socket\nsocket.socket()\n",
        caps=Capabilities(time_limit_s=5, net=False),
    )
    assert not res.ok
    assert "network" in (res.error or "").lower() or "PermissionError" in (res.error or "")


# --- filesystem guard ----------------------------------------------------


def test_write_outside_scratch_blocked():
    res = run(
        "open('/etc/athena_evil.txt', 'w').write('x')",
        caps=Capabilities(time_limit_s=5),
    )
    assert not res.ok
    assert "not permitted" in (res.error or "") or "PermissionError" in (res.error or "")


def test_read_outside_allowlist_blocked():
    res = run(
        "open('/etc/passwd').read()",
        caps=Capabilities(time_limit_s=5),
    )
    assert not res.ok
    assert "not permitted" in (res.error or "") or "PermissionError" in (res.error or "")


def test_scratch_read_write_allowed():
    code = (
        "def main():\n"
        "    with open('note.txt', 'w') as f:\n"
        "        f.write('persisted')\n"
        "    with open('note.txt') as f:\n"
        "        return f.read()\n"
    )
    res = run(code, caps=Capabilities(time_limit_s=5), entrypoint="main")
    assert res.ok
    assert res.return_value == "persisted"


# --- environment isolation ----------------------------------------------


def test_parent_env_not_leaked(monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_PARENT_VAR", "leaked-value")
    res = run(
        "import os\ndef main():\n    return os.environ.get('SUPER_SECRET_PARENT_VAR')\n",
        caps=Capabilities(time_limit_s=5),
        entrypoint="main",
    )
    assert res.ok
    assert res.return_value is None


# --- kill switch integration --------------------------------------------


def test_halted_refuses_to_run():
    safety.set_mode("halted")
    res = run("print('should not run')", caps=Capabilities(time_limit_s=5))
    assert not res.ok
    assert res.killed_reason == "halted"
    assert "should not run" not in res.stdout


def test_dry_run_skips_execution():
    safety.set_mode("dry_run")
    res = run("print('should not run')", caps=Capabilities(time_limit_s=5))
    assert res.ok
    assert "dry-run" in res.stdout
    assert "should not run" not in res.stdout
