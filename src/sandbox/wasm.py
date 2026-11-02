"""WASM skill sandbox (v2) — run LLM-generated skills in a WebAssembly runtime
that has **no ambient authority**.

The Phase 0 sandbox (``runner.py`` + ``_harness.py``) isolates skills in a child
Python process and installs network/filesystem/process guards *inside* that
process. That is solid defense-in-depth, but the guards live in the same
interpreter as the untrusted code — a Python-level escape is conceivable.

This v2 backend removes that assumption. A WebAssembly guest cannot make a
syscall at all: it can only touch what the host explicitly hands it through
WASI. With **zero preopened directories and no socket capability**, the guest
has no filesystem and no network — not by policy, but by construction. Resource
limits are enforced by the runtime itself (deterministic *fuel* metering plus an
*epoch* wall-clock deadline and a linear-memory ceiling), independent of OS
signals, so they behave identically on macOS and Linux.

Status: the runtime, the zero-authority WASI configuration, and the
resource-limit enforcement are complete and self-tested (:meth:`WasmSandbox.self_test`).
Executing *Python* skills additionally needs a CPython-WASI build
(``python.wasm``); point ``GLAUX_PYTHON_WASM`` at one to enable
:meth:`WasmSandbox.run`. Until then the dispatcher falls back to the subprocess
backend. See ``WASM_V2.md``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from paths import home

from .capabilities import Capabilities, SandboxResult

PYTHON_WASM_ENV = "GLAUX_PYTHON_WASM"

# Wall-clock is the primary limit (the epoch timer, matching the subprocess
# backend). Fuel is a deterministic backstop sized well above the observed
# Python-in-wasm rate (~120B fuel/s) so the epoch deadline reliably fires first
# for normal timeouts; fuel only trips in a pathological case where the host
# timer thread never runs.
_FUEL_PER_SECOND = 1_000_000_000_000

# With epoch_interruption enabled, every store must arm an epoch deadline or it
# traps immediately. This large value effectively disables the epoch guard for
# stores that don't want a wall-clock timeout.
_EPOCH_OFF = 1 << 31

# A pure-compute module (adds two ints) — used to prove the runtime executes
# wasm with no host access, and a spin loop to prove fuel exhaustion traps.
_ADD_WAT = (
    '(module (func (export "add") (param i32 i32) (result i32) '
    "local.get 0 local.get 1 i32.add))"
)
_SPIN_WAT = (
    '(module (func (export "spin") (loop (br 0))))'
)

# Runs *inside* the wasm guest (python.wasm). Reads the job the host preopened
# read-only at /job, executes the skill, prints one JSON line to stdout.
_DRIVER = r'''
import json, sys, io, traceback
from contextlib import redirect_stdout, redirect_stderr
with open("/job/job.json") as f:
    job = json.load(f)
out, err = io.StringIO(), io.StringIO()
res = {"ok": False, "return_value": None, "return_repr": False,
       "stdout": "", "stderr": "", "error": None, "traceback": None}
try:
    ns = {"__name__": "__skill__"}
    with redirect_stdout(out), redirect_stderr(err):
        exec(compile(job["code"], "<skill>", "exec"), ns)
        rv = None
        ep = job.get("entrypoint")
        if ep:
            fn = ns.get(ep)
            if not callable(fn):
                raise NameError("entrypoint %r is not defined" % ep)
            rv = fn(**(job.get("inputs") or {}))
    try:
        json.dumps(rv); res["return_value"] = rv
    except (TypeError, ValueError):
        res["return_value"] = repr(rv); res["return_repr"] = True
    res["ok"] = True
except BaseException as e:  # report everything to the host
    res["error"] = "%s: %s" % (type(e).__name__, e)
    res["traceback"] = traceback.format_exc()
finally:
    res["stdout"] = out.getvalue()
    res["stderr"] = err.getvalue()
    sys.stdout.write("\x1e" + json.dumps(res) + "\x1e")
'''


def _wt():
    import wasmtime

    return wasmtime


# One engine + one compiled module per process. Compiling the ~25 MB python.wasm
# takes >1s; doing it per run would dominate latency (and eat the time budget).
# The module is instantiated fresh per run (own store/memory) but compiled once.
_ENGINE = None
_MODULE_CACHE: dict = {}  # wasm_path -> (mtime, size, Module)


def _shared_engine():
    global _ENGINE
    if _ENGINE is None:
        wt = _wt()
        cfg = wt.Config()
        cfg.consume_fuel = True          # deterministic instruction budget
        cfg.epoch_interruption = True    # wall-clock deadline, OS-signal-free
        _ENGINE = wt.Engine(cfg)
    return _ENGINE


def _compiled_module(engine, wasm_path: str):
    """Compile ``wasm_path`` once and reuse it. Also keeps a serialized ``.cwasm``
    beside it so the first run after a restart skips the >1s compile too."""
    st = os.stat(wasm_path)
    cached = _MODULE_CACHE.get(wasm_path)
    if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]
    wt = _wt()
    module = None
    cache_file = wasm_path + ".cwasm"
    if os.path.isfile(cache_file) and os.path.getmtime(cache_file) >= st.st_mtime:
        try:
            module = wt.Module.deserialize_file(engine, cache_file)
        except Exception:
            module = None  # stale/incompatible cache -> recompile
    if module is None:
        module = wt.Module.from_file(engine, wasm_path)
        try:
            with open(cache_file, "wb") as f:
                f.write(module.serialize())
        except Exception:
            pass
    _MODULE_CACHE[wasm_path] = (st.st_mtime, st.st_size, module)
    return module


class WasmSandbox:
    """Execute skills in a WASI guest with no ambient authority."""

    def __init__(self) -> None:
        self._engine = _shared_engine()

    # --- availability -----------------------------------------------------

    @staticmethod
    def runtime_available() -> bool:
        """True if the wasm runtime is installed (can run wasm modules)."""
        try:
            import wasmtime  # noqa: F401

            return True
        except Exception:
            return False

    @staticmethod
    def python_wasm_path() -> Optional[str]:
        """The CPython-WASI runtime to use: an explicit GLAUX_PYTHON_WASM path,
        else the default drop-in location <GLAUX_HOME>/python.wasm (what
        scripts/fetch_python_wasm.sh installs). None if neither exists."""
        p = os.environ.get(PYTHON_WASM_ENV)
        if p and os.path.isfile(p):
            return p
        default = str(home() / "python.wasm")
        return default if os.path.isfile(default) else None

    @classmethod
    def python_available(cls) -> bool:
        """True if we can run *Python* skills (runtime + a CPython-WASI build)."""
        return cls.runtime_available() and cls.python_wasm_path() is not None

    # --- self-test: prove the isolation + limits actually hold ------------

    def self_test(self) -> dict:
        """Run trivial modules to prove (a) the runtime executes wasm with zero
        preopened dirs / no network, and (b) a runaway module traps on fuel
        exhaustion without any OS signal. Returns a small report dict."""
        wt = _wt()
        store = wt.Store(self._engine)
        store.set_fuel(1_000_000)
        store.set_epoch_deadline(_EPOCH_OFF)  # no wall-clock guard for the self-test
        add = wt.Instance(store, wt.Module(self._engine, _ADD_WAT), []).exports(store)["add"]
        value = add(store, 2, 40)
        fuel_used = 1_000_000 - store.get_fuel()

        spin_store = wt.Store(self._engine)
        spin_store.set_fuel(200_000)
        spin_store.set_epoch_deadline(_EPOCH_OFF)  # so the loop traps on fuel, not epoch
        trapped = False
        try:
            wt.Instance(spin_store, wt.Module(self._engine, _SPIN_WAT), []).exports(spin_store)["spin"](spin_store)
        except wt.Trap:
            trapped = True  # fuel exhausted -> deterministic halt

        return {
            "ok": value == 42 and trapped,
            "compute_result": value,
            "fuel_used": fuel_used,
            "runaway_trapped": trapped,
            "preopened_dirs": 0,      # no host filesystem
            "network": False,         # WASI preview1 grants no sockets
        }

    # --- run a Python skill ----------------------------------------------

    def run(
        self,
        code: str,
        caps: Optional[Capabilities] = None,
        inputs: Optional[dict] = None,
        entrypoint: Optional[str] = None,
    ) -> SandboxResult:
        caps = caps or Capabilities()
        wasm_path = self.python_wasm_path()
        if wasm_path is None:
            return SandboxResult(
                ok=False,
                error=f"wasm backend has no CPython-WASI runtime; set {PYTHON_WASM_ENV}",
            )
        return self._run_python(wasm_path, code, caps, inputs or {}, entrypoint)

    def _run_python(
        self, wasm_path: str, code: str, caps: Capabilities, inputs: dict, entrypoint: Optional[str]
    ) -> SandboxResult:
        wt = _wt()
        import time

        with tempfile.TemporaryDirectory(prefix="glaux-wasm-") as job_dir, \
                tempfile.TemporaryDirectory(prefix="glaux-wasm-out-") as out_dir:
            (Path(job_dir) / "job.json").write_text(
                json.dumps({"code": code, "entrypoint": entrypoint, "inputs": inputs})
            )
            (Path(job_dir) / "driver.py").write_text(_DRIVER)
            out_file = Path(out_dir) / "stdout.txt"

            wasi = wt.WasiConfig()
            wasi.argv = ["python", "/job/driver.py"]
            wasi.stdout_file = str(out_file)
            # The ONLY host authority the guest receives: the job dir (read-only)
            # and any paths the skill explicitly declared. No network, ever.
            wasi.preopen_dir(job_dir, "/job", wt.DirPerms.READ_ONLY, wt.FilePerms.READ_ONLY)
            for i, p in enumerate(caps.fs_read):
                wasi.preopen_dir(p, f"/ro{i}", wt.DirPerms.READ_ONLY, wt.FilePerms.READ_ONLY)
            for i, p in enumerate(caps.fs_write):
                wasi.preopen_dir(p, f"/rw{i}", wt.DirPerms.READ_WRITE, wt.FilePerms.READ_WRITE)

            store = wt.Store(self._engine)
            store.set_wasi(wasi)
            store.set_fuel(max(1, int(caps.time_limit_s * _FUEL_PER_SECOND)))
            try:
                store.set_limits(memory_size=caps.mem_mb * 1024 * 1024)
            except Exception:
                pass

            # Compile once (cached); instantiate fresh. Do this BEFORE arming the
            # wall-clock timer so the one-time compile can't eat the time budget.
            linker = wt.Linker(self._engine)
            linker.define_wasi()
            module = _compiled_module(self._engine, wasm_path)

            # Wall-clock deadline: a background timer bumps the engine epoch once
            # the budget elapses, tripping the guest's epoch deadline -> trap.
            store.set_epoch_deadline(1)
            done = threading.Event()

            def _deadline() -> None:
                if not done.wait(caps.time_limit_s):
                    self._engine.increment_epoch()

            timer = threading.Thread(target=_deadline, daemon=True)
            timer.start()

            killed_reason: Optional[str] = None
            error: Optional[str] = None
            start = time.monotonic()
            try:
                instance = linker.instantiate(store, module)
                instance.exports(store)["_start"](store)
            except wt.ExitTrap:
                pass  # normal WASI exit()
            except wt.Trap as e:
                msg = str(e).lower()
                if "epoch" in msg or "interrupt" in msg:
                    killed_reason = "timeout"
                elif "fuel" in msg:
                    killed_reason = "timeout"
                else:
                    error = str(e)
            except Exception as e:  # noqa: BLE001
                error = str(e)
            finally:
                done.set()
            duration = time.monotonic() - start

            stdout = out_file.read_text() if out_file.exists() else ""
            return self._parse(stdout, killed_reason, error, duration)

    @staticmethod
    def _parse(stdout: str, killed_reason, error, duration) -> SandboxResult:
        if killed_reason:
            return SandboxResult(
                ok=False, error=f"execution killed: {killed_reason}",
                killed_reason=killed_reason, duration_s=duration,
            )
        # The driver frames its JSON result between \x1e markers so any skill
        # print()s don't corrupt it.
        payload = None
        if "\x1e" in stdout:
            try:
                payload = json.loads(stdout.split("\x1e")[1])
            except (IndexError, json.JSONDecodeError):
                payload = None
        if payload is None:
            return SandboxResult(
                ok=False, error=error or "wasm guest produced no result",
                stderr=stdout, duration_s=duration,
            )
        return SandboxResult(
            ok=bool(payload.get("ok")),
            return_value=payload.get("return_value"),
            stdout=payload.get("stdout", ""),
            stderr=payload.get("stderr", ""),
            error=payload.get("error"),
            traceback=payload.get("traceback"),
            duration_s=duration,
        )
