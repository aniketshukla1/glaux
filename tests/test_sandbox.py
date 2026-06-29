"""Phase 0.2: skill sandbox isolation and resource limits."""

from __future__ import annotations

import os

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


# --- runtime process / fs-bypass hardening (moat #2) ---------------------


def test_os_system_blocked():
    res = run("import os\nos.system('echo pwned > /tmp/ath_pwn_sys')", caps=Capabilities(time_limit_s=5))
    assert not res.ok
    assert "process" in (res.error or "").lower()
    assert not os.path.exists("/tmp/ath_pwn_sys")


def test_subprocess_blocked_even_via_dynamic_import():
    code = "m = __import__('subprocess')\nm.run(['echo', 'x'])\n"
    res = run(code, caps=Capabilities(time_limit_s=5))
    assert not res.ok
    assert "process" in (res.error or "").lower()


def test_os_open_write_escape_blocked():
    target = "/tmp/ath_pwn_osopen"
    code = (
        "import os\n"
        f"fd = os.open({target!r}, os.O_WRONLY | os.O_CREAT)\n"
        "os.write(fd, b'x'); os.close(fd)\n"
    )
    res = run(code, caps=Capabilities(time_limit_s=5))
    assert not res.ok
    assert "not permitted" in (res.error or "").lower()
    assert not os.path.exists(target)


def test_os_remove_outside_scratch_blocked():
    # create a real file the skill must not be able to delete
    victim = "/tmp/ath_victim_keep"
    with open(victim, "w") as f:
        f.write("keep me")
    try:
        res = run(f"import os\nos.remove({victim!r})", caps=Capabilities(time_limit_s=5))
        assert not res.ok
        assert os.path.exists(victim)  # not deleted
    finally:
        os.remove(victim)


def test_writes_into_scratch_still_allowed():
    # a skill may use its scratch dir freely
    code = "open('out.txt', 'w').write('ok')\nprint(open('out.txt').read())"
    res = run(code, caps=Capabilities(time_limit_s=5))
    assert res.ok
    assert "ok" in res.stdout
