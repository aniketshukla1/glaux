"""WASM sandbox v2: zero-ambient-authority runtime + backend dispatch.

The Python-skill execution path needs a CPython-WASI build (``python.wasm``),
which isn't bundled, so those cases are covered by the self-test/dispatch
behavior here; when ``GLAUX_PYTHON_WASM`` is configured the same ``run`` path
executes real skills inside the guest.
"""

from __future__ import annotations

import pytest

pytest.importorskip("wasmtime")  # skip the whole module if the runtime is absent

import safety  # noqa: E402
from sandbox import Capabilities, WasmSandbox, run  # noqa: E402


@pytest.fixture(autouse=True)
def _live_mode():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def test_runtime_available():
    assert WasmSandbox.runtime_available() is True


def test_self_test_proves_isolation_and_fuel_trap():
    report = WasmSandbox().self_test()
    assert report["ok"] is True
    assert report["compute_result"] == 42          # wasm actually executed
    assert report["runaway_trapped"] is True        # fuel exhaustion halts a runaway loop
    assert report["preopened_dirs"] == 0            # guest gets no host filesystem
    assert report["network"] is False               # guest gets no sockets


def test_python_unavailable_without_a_configured_runtime(monkeypatch):
    monkeypatch.delenv("GLAUX_PYTHON_WASM", raising=False)
    assert WasmSandbox.python_available() is False
    res = WasmSandbox().run("def main():\n    return 1\n", entrypoint="main")
    assert not res.ok
    assert "GLAUX_PYTHON_WASM" in (res.error or "")


def test_auto_backend_falls_back_to_subprocess(monkeypatch):
    # With no python.wasm available, "auto" must transparently run the skill on
    # the subprocess backend rather than failing.
    monkeypatch.delenv("GLAUX_PYTHON_WASM", raising=False)
    monkeypatch.setenv("GLAUX_SANDBOX_BACKEND", "auto")
    res = run(
        "def main(x):\n    return x * 2\n",
        caps=Capabilities(time_limit_s=5),
        inputs={"x": 21},
        entrypoint="main",
    )
    assert res.ok
    assert res.return_value == 42


def test_strict_wasm_refuses_rather_than_weakening_isolation(monkeypatch):
    # "wasm" must NOT silently downgrade to the weaker subprocess sandbox.
    monkeypatch.delenv("GLAUX_PYTHON_WASM", raising=False)
    monkeypatch.setenv("GLAUX_SANDBOX_BACKEND", "wasm")
    res = run("def main():\n    return 1\n", caps=Capabilities(time_limit_s=5), entrypoint="main")
    assert not res.ok
    assert "wasm" in (res.error or "").lower()


requires_python_wasm = pytest.mark.skipif(
    not WasmSandbox.python_available(),
    reason="no CPython-WASI runtime (run scripts/fetch_python_wasm.sh or set GLAUX_PYTHON_WASM)",
)


@requires_python_wasm
def test_real_skill_executes_in_wasm_guest():
    sb = WasmSandbox()
    code = (
        "def run(s):\n"
        "    vals = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n"
        "    total = prev = 0\n"
        "    for ch in reversed(str(s).upper()):\n"
        "        v = vals.get(ch, 0); total += -v if v < prev else v; prev = v\n"
        "    return total\n"
    )
    res = sb.run(code, caps=Capabilities(time_limit_s=10), inputs={"s": "MCMXCIV"}, entrypoint="run")
    assert res.ok
    assert res.return_value == 1994


@requires_python_wasm
def test_wasm_guest_has_no_network_or_host_fs():
    sb = WasmSandbox()
    net = sb.run(
        "import socket\ndef run():\n    return socket.socket().connect(('1.1.1.1', 80))\n",
        caps=Capabilities(time_limit_s=10), entrypoint="run",
    )
    assert not net.ok  # no sockets exist in the guest
    fs = sb.run(
        "def run():\n    return open('/etc/passwd').read()\n",
        caps=Capabilities(time_limit_s=10), entrypoint="run",
    )
    assert not fs.ok  # /etc was never preopened -> unreachable


@requires_python_wasm
def test_wasm_wall_clock_timeout():
    sb = WasmSandbox()
    res = sb.run("def run():\n    while True:\n        pass\n", caps=Capabilities(time_limit_s=2), entrypoint="run")
    assert not res.ok
    assert res.killed_reason == "timeout"
    assert res.duration_s < 4  # bounded near the 2s budget, not hung


def test_default_backend_runs_skill(monkeypatch):
    # No env set -> default "auto". With no CPython-WASI runtime in the test env
    # it transparently falls back to the subprocess sandbox; the skill still runs.
    monkeypatch.delenv("GLAUX_SANDBOX_BACKEND", raising=False)
    monkeypatch.delenv("GLAUX_PYTHON_WASM", raising=False)
    res = run(
        "def main():\n    return 'ok'\n",
        caps=Capabilities(time_limit_s=5),
        entrypoint="main",
    )
    assert res.ok
    assert res.return_value == "ok"
