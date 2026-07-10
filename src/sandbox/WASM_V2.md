# Skill Sandbox v2 — WebAssembly (no ambient authority)

The v1 sandbox (`runner.py` + `_harness.py`) runs each skill in a **child Python
process** with a minimal environment, resource rlimits, a parent-side
memory/timeout watcher, and network/filesystem/process guards installed *inside*
that process. It's strong defense-in-depth, and it's what runs by default.

Its one structural weakness: the guards live in the **same interpreter** as the
untrusted code. They close every escape we know of (see the adversarial tests in
`tests/test_sandbox.py`), but they are policy inside the guest, not a wall
around it.

**v2 removes that assumption.** Skills run in a **WebAssembly guest** that
physically cannot issue a syscall. It can only touch what the host hands it
through WASI. We hand it nothing by default:

- **No filesystem** — zero preopened directories. A skill sees only the paths it
  explicitly declared in its capabilities (`fs_read` → read-only preopen,
  `fs_write` → read-write preopen), each mounted at a synthetic guest path.
- **No network** — WASI preview 1 grants no sockets. There is no code path from
  guest to host network.
- **Deterministic resource limits, no OS signals** — a *fuel* budget caps total
  instructions (a runaway loop traps deterministically), an *epoch* deadline
  enforces wall-clock time, and a linear-memory ceiling caps RAM. These behave
  identically on macOS and Linux (v1's memory kill relies on polling `ps`
  because macOS ignores `RLIMIT_AS`).

## What's built

- `wasm.py::WasmSandbox` — the engine, the zero-authority WASI configuration,
  the resource-limit wiring, and the Python-skill execution path. **Real Python
  skills run end-to-end** in the guest (verified: `roman_to_int("MCMXCIV") ==
  1994`, network/`/etc` access denied, wall-clock timeout enforced).
- **Compiled-module cache** — the ~25 MB `python.wasm` compiles once per process
  (>1s) and is reused across runs; a serialized `.cwasm` beside it skips the
  compile even on the first run after a restart. Warm skill execution is ~0.1s.
- `WasmSandbox.self_test()` — proves, at runtime, that the guest executes wasm
  with **0 preopened dirs / no network** and that a runaway module **traps on
  fuel exhaustion**. Exercised by `tests/test_sandbox_wasm.py`.
- Backend dispatch in `runner.py`, selected by `ATHENA_SANDBOX_BACKEND`:
  - unset / `auto` → **default**: use WASM when a CPython-WASI runtime is present,
    else transparently fall back to the subprocess sandbox;
  - `wasm` → require the WASM backend; **refuse to run** if it can't (never
    silently downgrade isolation);
  - `subprocess` → force the v1 sandbox.

## Enabling Python-skill execution

The runtime + isolation + Python execution are done. The one thing not committed
to git is the ~25 MB CPython-WASI binary. Install it once:

```bash
scripts/fetch_python_wasm.sh    # pinned + checksum-verified -> ~/.athena/python.wasm
```

That's it — the backend defaults to `auto`, so with the runtime present every
skill the eval harness and synthesizer run executes inside the WASM guest via the
same `sandbox.run(...)` entry point. Override the location with
`ATHENA_PYTHON_WASM=/path/to/python.wasm` if you keep it elsewhere. `/api/health`
reports `sandbox.active == "wasm"` and the Studio Skills panel shows the badge.

## Roadmap

- Optionally vendor/produce the `python.wasm` at build time so no fetch step is
  needed (today it's a one-line script, kept out of git to avoid a 25 MB blob).
- Wall-clock limits use an epoch timer; fuel is a generous backstop. Could add a
  per-skill instruction *budget* (deterministic replay) as a separate cap.
- Move from WASI preview 1 to the **component model** (preview 2) for typed,
  capability-scoped host imports (e.g. a metered HTTP import when `net=True`)
  instead of the current all-or-nothing socket model.
