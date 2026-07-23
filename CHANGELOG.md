# Changelog

All notable changes to Athena are documented here. This project follows
[Semantic Versioning](https://semver.org/).

The stable public surface is the **`athena` CLI** and the **HTTP API**. Internal Python
modules (`agents.*`, `core.*`, …) may change within a minor release.

## [1.0.0] — first public release

The initial open-source release.

### Swarm
- Router plans a specialist team per directive; steps execute in parallel across a
  dependency graph; a reflector verifies and a lead synthesizes the final answer.
- Three-tier routing (fast / medium / full) chosen by a local embedding classifier —
  sub-millisecond, no model call — so trivial asks skip planning and reflection.
- Intra-turn parallel tool calls.

### Trust
- Every reasoning step, tool call, and self-modification is Ed25519-signed by the acting
  agent and appended to a hash-chained ledger; `athena verify` validates the chain.
- Per-agent cryptographic identities with capability tokens for cross-agent handoff.

### Skills
- Runtime tool synthesis: when nothing fits, Athena writes a skill, static
  capability-checks it, runs its generated tests in the sandbox, and uses it in the
  same run.
- Self-healing: a skill that fails with a logic error is repaired, re-tested, retried.
- Lifecycle: quarantine → promotion → deprecation, with human approval in gated mode.

### Sandbox & workspace
- WebAssembly sandbox (wasmtime) with zero ambient authority, fuel and wall-clock limits.
- Opt-in jailed workspace with `write/read/list/mkdir/delete/edit_file/glob/grep`,
  per-file and total size caps, and traversal/symlink guards.

### Self-evolving harness
- Six evidence-gated, ledger-signed, reversible operators: tier-routing exemplars,
  per-specialist iteration budgets, prompt lessons from recurring failures, distilled
  playbooks, promotion of proven skills to permanent tools, and retirement of
  chronically-failing specialists.
- Optional auto-evolve cadence.

### Cost & context
- Budget-bounded history compaction for long runs, signed to the ledger.
- Prompt caching, model tiering (cheap model for routing/reflection).
- Opt-in semantic answer cache: a near-identical directive returns the prior answer
  with zero LLM calls.

### Extensibility
- Authored playbooks; user-defined sub-agents merged into the router's roster.
- MCP tool servers; browser and computer control.
- 30+ model providers, plus fully local operation via Ollama.

### Interfaces
- Web dashboard, a full-parity `athena` CLI, a desktop app, and messaging gateways.

[1.0.0]: https://github.com/athena-swarm/athena/releases/tag/v1.0.0
