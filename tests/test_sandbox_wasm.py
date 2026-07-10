"""WASM sandbox v2: zero-ambient-authority runtime + backend dispatch.

The Python-skill execution path needs a CPython-WASI build (``python.wasm``),
which isn't bundled, so those cases are covered by the self-test/dispatch
behavior here; when ``ATHENA_PYTHON_WASM`` is configured the same ``run`` path
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
    monkeypatch.delenv("ATHENA_PYTHON_WASM", raising=False)
    assert WasmSandbox.python_available() is False
    res = WasmSandbox().run("def main():\n    return 1\n", entrypoint="main")
    assert not res.ok
    assert "ATHENA_PYTHON_WASM" in (res.error or "")


def test_auto_backend_falls_back_to_subprocess(monkeypatch):
    # With no python.wasm available, "auto" must transparently run the skill on
    # the subprocess backend rather than failing.
    monkeypatch.delenv("ATHENA_PYTHON_WASM", raising=False)
    monkeypatch.setenv("ATHENA_SANDBOX_BACKEND", "auto")
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
    monkeypatch.delenv("ATHENA_PYTHON_WASM", raising=False)
    monkeypatch.setenv("ATHENA_SANDBOX_BACKEND", "wasm")
    res = run("def main():\n    return 1\n", caps=Capabilities(time_limit_s=5), entrypoint="main")
    assert not res.ok
    assert "wasm" in (res.error or "").lower()


def test_default_backend_is_subprocess(monkeypatch):
    # No env set -> the well-tested subprocess backend, unchanged.
    monkeypatch.delenv("ATHENA_SANDBOX_BACKEND", raising=False)
    res = run(
        "def main():\n    return 'ok'\n",
        caps=Capabilities(time_limit_s=5),
        entrypoint="main",
    )
    assert res.ok
    assert res.return_value == "ok"
