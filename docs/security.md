# Security model

Athena executes model-written code, so isolation is a core feature rather than an
afterthought. This page describes what the system defends and what it deliberately does
not. To *report* a vulnerability, see
[SECURITY.md](https://github.com/athena-swarm/athena/blob/main/SECURITY.md).

## Layers

### 1. Static capability check
Before a synthesized skill ever runs, its source is checked against the capabilities it
declared. Code reaching for authority it wasn't granted (network, filesystem, process
spawning) is rejected — it never reaches execution.

### 2. The sandbox
Skills run in a **WebAssembly guest with no ambient authority**: it cannot syscall by
default, so there is nothing to escape *to* unless a capability was explicitly granted.
Runaway code is bounded by both fuel (instruction budget) and wall-clock limits. A
hardened subprocess sandbox is the fallback backend where WASM isn't available.

This has been exercised adversarially — attempts to open sockets, read `/etc/passwd`, or
spin in an infinite loop are contained.

### 3. The workspace jail
File access is a *separate*, opt-in capability. When enabled, reads and writes are
confined to one directory, with per-file and total size caps, and guards against path
traversal, absolute paths, and symlinks pointing outside. The workspace root itself
cannot be deleted.

### 4. Identity and capability tokens
Each agent holds an Ed25519 keypair. Cross-agent delegation carries a capability token
that the receiving agent verifies — it refuses work that wasn't issued to it, is expired,
or is for a capability it wasn't granted.

### 5. The ledger
Every action is signed by the acting agent and hash-chained. Undetected tampering means
breaking the chain. `athena verify` checks it. This is what makes "prove it" more than a
slogan: you can demonstrate what the system did, including how it modified itself.

### 6. Human-in-the-loop controls
- `athena approval gated` — a human approves each synthesized skill before it can run.
- `athena safety dry-run` — execute reasoning, skip side effects.
- `athena safety halted` — stop all execution.
- Self-modification is gated, signed, and reversible by design.

## Deliberate trade-offs

These are design decisions, not gaps:

- **The workspace grants real file access** inside its jail when you enable it. That is
  its purpose; the boundary is the jail, not the absence of access.
- **MCP servers you connect run with the authority you give them.** Athena cannot sandbox
  a third-party tool server — treat connecting one like installing a plugin.
- **The semantic answer cache cannot see conversation context**, so it is off by default
  and its similarity threshold is deliberately strict. Time-sensitive directives are
  never cached.
- **`dry-run` and `halted` are cooperative controls** over the swarm's own execution
  path. They are not a containment mechanism against code that has already escaped the
  sandbox — that is the sandbox's job.

## Handling secrets

API keys live in your environment or under `ATHENA_HOME` (git-ignored) and are never
written to the ledger or logs. Skill arguments are truncated before being signed, so a
large payload can't bloat — or leak through — a block. A secrets broker mediates skill
access to credentials rather than handing them to guest code.

## Operating Athena safely

- Start with capabilities off; enable only what a workload needs.
- Use `approval gated` when running untrusted or high-stakes directives.
- Keep `ATHENA_API_SECRET` set if the server is reachable beyond localhost.
- Run `athena verify` as part of any audit.
