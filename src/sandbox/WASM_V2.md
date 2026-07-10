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
  the resource-limit wiring, and the Python-skill execution path.
- `WasmSandbox.self_test()` — proves, at runtime, that the guest executes wasm
  with **0 preopened dirs / no network** and that a runaway module **traps on
  fuel exhaustion**. Exercised by `tests/test_sandbox_wasm.py`.
- Backend dispatch in `runner.py`, selected by `ATHENA_SANDBOX_BACKEND`:
  - unset / `subprocess` → the v1 sandbox (**default, unchanged**);
  - `wasm` → require the WASM backend; **refuse to run** if it can't (never
    silently downgrade isolation);
  - `auto` → use WASM when a Python runtime is available, else fall back to v1.

## Enabling Python-skill execution

The runtime and isolation are done; running *Python* skills needs a CPython
compiled to WASI (`python.wasm`), which we don't bundle (~20 MB). To enable:

1. `pip install wasmtime` (already in `requirements.txt`).
2. Obtain a CPython-WASI build — e.g. the VMware Labs
   `webassembly-language-runtimes` release, or a `componentize-py` toolchain.
3. Point Athena at it and turn the backend on:

   ```bash
   export ATHENA_PYTHON_WASM=/path/to/python.wasm
   export ATHENA_SANDBOX_BACKEND=auto   # or: wasm (strict)
   ```

Every skill the eval harness and the synthesizer run then executes inside the
WASM guest, through the exact same `sandbox.run(...)` entry point — no other
code changes.

## Roadmap

- Ship a pinned, checksummed `python.wasm` (or produce one at build time) so the
  Python path is on by default.
- Precompile skills to a module cache (`Engine` supports serialized modules) to
  cut per-run instantiation cost.
- Move from WASI preview 1 to the **component model** (preview 2) for typed,
  capability-scoped host imports (e.g. a metered HTTP import when `net=True`)
  instead of the current all-or-nothing socket model.
