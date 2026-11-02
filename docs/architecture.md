# Architecture

Glaux turns a goal into a **swarm** and signs everything it does.

```
directive
   │
   ├─ tier router  (local embedding classifier, sub-millisecond, no model call)
   │     ├─ fast   → one tool-free responder
   │     ├─ medium → one capable tool-using agent
   │     └─ full   → the planned swarm ↓
   │
   ├─ router      plans a team + a dependency graph
   ├─ specialists execute level-by-level, in parallel
   ├─ reflector   verifies each step, sends work back if needed
   └─ lead        synthesizes the final answer
             ↓
        every step Ed25519-signed → hash-chained ledger
```

## The tiers

Not every question deserves a committee. An embedding classifier (feature-hashing
bag-of-words, nearest-exemplar — deterministic and model-free) picks the cheapest tier
that can do the job, and the [self-evolving harness](self-evolution.md) improves that
choice from real outcomes.

## The swarm

The **router** reads a one-line description of every specialist and composes a team plus
a dependency graph. Steps are topologically sorted into levels; everything in a level is
independent, so it runs concurrently. The **reflector** grades each step and can send it
back for another attempt. A **lead** integrates the results into an answer to the
*original* directive.

The built-in roster (researcher, web, scientist, analyst, coder, engineer, tester,
writer) is data-driven — and you can add your own with `glaux subagents add`, which the
router will dispatch to like any other.

## The ledger

Every agent is a cryptographic identity (Ed25519). Every reasoning step, tool call,
skill synthesis, context compaction, and self-modification is signed by the acting agent
and appended as a block whose hash chains to the previous one. Change any block and
verification fails:

```bash
glaux verify   # ✓ chain verified · N signed blocks
```

The kernel is a native Rust crate (`native/glaux_ledger`) for speed, and appends are
thread-safe so parallel specialists can write concurrently.

## Skills and the sandbox

A **skill** is executable Python the swarm can call. When nothing fits, an agent emits
`create_skill`; Glaux synthesizes the code, runs a **static capability check** (rejecting
code that reaches for authority it wasn't granted), executes the auto-generated tests
**inside the sandbox**, and only then injects it into the live run.

Skills execute in a **WebAssembly guest with no ambient authority** — no syscalls by
default — with fuel and wall-clock limits. A subprocess sandbox is the fallback backend.

Skills have a lifecycle: `quarantined → promoted → deprecated`, driven by real usage.
A failing skill is **self-healed** (repaired, re-tested, retried), and a proven one can be
pinned as a permanent tool.

## Memory

Three layers, backed by AthenaDB:

- **semantic** — facts
- **episodic** — what happened
- **procedural** — skills, retrieved by similarity to the goal (pinned skills are always offered)

## Context management

A long run's history is compacted under a fixed character budget: recent steps verbatim,
older ones as one-line digests, the deepest elided. Deterministic (no extra model call),
and every compaction is signed.

## The workspace

Opt-in real file access, confined to one directory with per-file and total size caps and
guards against traversal, absolute paths, and symlinks. Tools: `write_file`, `read_file`,
`list_files`, `make_dir`, `delete_path`, `edit_file`, `glob`, `grep`.

## Interfaces

One FastAPI server exposes the HTTP API, streams runs over Server-Sent Events, and serves
the React dashboard. The `glaux` CLI is a stdlib-only client over the same API, and
there's a native desktop app and messaging gateways.

See also: [security model](security.md) · [self-evolving harness](self-evolution.md) ·
[HTTP API](api.md)
