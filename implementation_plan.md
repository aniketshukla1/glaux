# Athena Implementation Plan

A self-improving multi-agent swarm built on three pillars that competing frameworks lack:

1. **Cryptographic agent identity** — Ed25519 keypairs, signed actions, verifiable provenance.
2. **Sandboxed skill execution** — LLM-generated code runs in an isolated runtime, never in-process.
3. **Curated self-improvement** — synthesized skills must pass tests, dedup, and quarantine before joining the library.

The Rust vector core, tri-partite memory, ReAct loop, and React UI are the *substrate*. The three pillars above are the *differentiation*.

---

## Cross-Cutting Decisions

Decisions made upfront so phases don't re-litigate them.

| Concern              | Choice                                              | Why                                                                              |
|----------------------|------------------------------------------------------|----------------------------------------------------------------------------------|
| LLM provider         | Anthropic SDK (`claude-opus-4-7`, `claude-sonnet-4-6`) | Native tool use, prompt caching, fits the cryptographic-identity story.        |
| Skill sandbox        | `subprocess` + `resource` limits + seccomp (Phase 0); migrate to `wasmtime` (Phase 4) | Subprocess is fast to ship; WASM is the long-term safe answer.                  |
| Persistence          | Rust WAL + periodic snapshot to disk                | In-RAM-only AthenaDB loses the brain on restart — non-negotiable for "self-improving". |
| External tools       | MCP (Model Context Protocol) first-class            | Free ecosystem; the platform shouldn't reinvent every connector.                |
| Identity primitive   | Ed25519 keypair per agent; public key = agent_id    | Portable, verifiable, signature-based — turns "ledger" into a real trust system. |
| Concurrency          | `asyncio` end-to-end; long jobs queued (Phase 5)    | Swarms are inherently async; sync code paints us into a corner.                  |
| HTTP mode for AthenaDB | Build the Axum server but defer endpoints to Phase 5 | Don't carry dead optionality; only wire it up when a multi-service need is real. |
| Ledger core          | Native Rust crate `native/athena_ledger` (PyO3); agents stay Python | Hot path is auditing long chains (hashing + signature verification) — native. Agents/orchestration stay Python (runtime skill synthesis, I/O-bound). |
| LLM access           | All calls behind a single `src/llm/gateway.py` seam | Multi-model routing, fallback, and cost-based selection drop in later without touching agents. |
| Secrets              | Sandbox-injected via a broker; skill code never sees raw keys | Hardcoded/plaintext credentials are a future incident. Secrets are a capability, not an argument. |
| Content trust        | Every context string tagged `trusted` / `untrusted` | Retrieved memory + tool/MCP outputs are prompt-injection vectors; the boundary must exist from day one. |

---

## Foundational Invariants

Non-negotiable properties baked into the data model and runtime from the first commit. Each is cheap to design in now and a rearchitect to retrofit. The phase that first enforces each is tagged.

- [x] **Embedding-model version tag** (Phase 1/2) — every vector stores `embed_model_id`, and `search` can filter by it so similarity is never computed across embedding models. A re-embedding pipeline keys off this tag. *(Stored + filterable as of Phase 1.)*
- [x] **Record schema version** (Phase 2) — every memory record carries `schema_version`. Enables forward migration as episodic/procedural schemas evolve.
- [x] **Tenant / namespace field** (Phase 1) — every `Entry` carries `namespace` (default `"default"`) and `search` filters by it. Single-tenant today; multi-tenant later without touching every query.
- [x] **Durable, resumable execution** (Phase 3) — `BaseAgent` checkpoints its state to disk after every step; `run(resume=True)` continues from the last committed step, not from zero.
- [x] **Reproducibility envelope** (Phase 3) — each run records `{model_id, temperature, seed, prompt_hashes, skills_offered}`. *(retrieved_memory_hash to be added when memory is wired into the loop in 3.2.)*
- [x] **Key rotation & validity windows** (Phase 0/3) — agents rotate keys; the registry tracks each key's valid time range, and `Ledger.verify(registry=...)` checks every block's signing key against the window valid at its timestamp. So history keeps verifying across rotations, and a key used outside its window is caught.
- [ ] **Cost/budget guard** (Phase 3) — the agent loop checks a per-task token/USD budget before each LLM call and each skill run; exceeding it halts the task cleanly.
- [ ] **HITL approval gate** (Phase 3) — `REQUEST_APPROVAL` is a first-class action type alongside `CALL_SKILL` / `CALL_AGENT`. Irreversible or out-of-policy actions block on human approval, logged to the ledger.

---

## Phase 0 — Foundations: Identity & Sandbox Primitives ✅ COMPLETE

The two security-critical primitives that everything later depends on. Get these wrong and the rest of the stack inherits the flaws.

### 0.1 Cryptographic Identity (`src/identity/`)

- [x] `keypair.py` — Ed25519 keypair generation via `cryptography` lib. Persist private key to `~/.athena/agents/<agent_id>.key` with `0600` perms.
- [x] `agent_id` = base58-encoded public key. Stable, portable, unforgeable.
- [x] `sign(payload: bytes) -> Signature` and `verify(public_key, payload, signature) -> bool` helpers.
- [x] Capability tokens: `Token{ issuer, subject, capability, expires_at, signature }`. JSON-serializable, signed by issuer. (`tokens.py`, with nonce + subject/capability binding)
- [x] **Key rotation:** `rotate()` issues a new keypair and a signed rotation record `{old_pubkey, new_pubkey, rotated_at, signature_by_old}`. Identity (`agent_id`) stays stable; the registry (`registry.py`) stores key validity windows so blocks verify against the key valid at signing time.
- [x] **Namespace:** `AgentIdentity` carries an optional `namespace` (default `"default"`) so the multi-tenant story is a field, not a migration.
- [x] Test: round-trip sign/verify, expired token rejection, tampered payload detection, rotation chain verifies, signature from a superseded key still validates for blocks within its window. (`tests/test_identity.py`, 16 passing)

### 0.2 Skill Sandbox (`src/sandbox/`)

- [x] `runner.py` — `run(code, caps, inputs, entrypoint, broker) -> SandboxResult`.
- [x] Implementation v1: `subprocess` in its own session/process-group, minimal env (no parent-env leak), `resource.setrlimit` (CPU, FD count), in-harness network + filesystem guards; memory enforced by a parent-side RSS watcher (reliable on macOS where `RLIMIT_AS` is not).
- [x] `Capabilities` declaration: `{net, fs_read, fs_write, time_limit_s, mem_mb, secrets}`. Default deny.
- [x] Capture: `stdout`, `stderr`, return value, exit code, wall time, peak RSS.
- [x] Test suite: infinite loop killed at time limit; memory bomb killed at RSS limit; network blocked; FS read/write outside allowlist blocked; scratch allowed; parent env not leaked; kill-switch honored. (`tests/test_sandbox.py`, 13 passing)
- [ ] **Migration note (deferred to Phase 4):** v2 swaps subprocess for `wasmtime` + Pyodide bundle. The `run()` interface is the seam so the swap is a one-file change.

### 0.3 Kill Switch & Dry-Run (`src/safety.py`)

- [x] Global `SAFETY_MODE` env (`ATHENA_SAFETY_MODE`): `live | dry_run | halted`, with a programmatic override that beats the env var.
- [x] `halted` short-circuits sandbox execution; the runner returns `killed_reason="halted"` rather than execute. (Wires into `CALL_SKILL`/`CALL_AGENT` in Phase 3.)
- [x] `dry_run` skips sandbox execution and returns a "would run" marker. Critical for debugging self-modification. (`tests/test_safety.py`, 4 passing)

### 0.4 Secrets Broker (`src/sandbox/secrets.py`)

- [x] `SecretsBroker` resolves named secrets from a pluggable backend (`DictSecretsBackend`, `EnvSecretsBackend`; file/keychain backends slot in later) at sandbox-launch time.
- [x] Secrets are injected into the sandbox as scoped env vars **only if** the skill's capabilities declare `secrets: [...]`. Skill code never receives raw keys as arguments and never sees undeclared secrets (verified by the minimal-env isolation test).
- [x] Redaction: any declared secret value is scrubbed from captured `stdout` / `stderr` / return values before they re-enter the reasoning window or the ledger.
- [x] Test: undeclared secret is absent from the sandbox env; declared secret resolves; secret value never appears in captured output; missing broker / unknown secret fail cleanly. (`tests/test_secrets.py`, 6 passing)

**Phase 0 exit criteria — ✅ MET (39 tests passing):** I can sign a payload, verify it, rotate a key and still verify old signatures, issue/verify capability tokens, run hostile Python in a sandbox without it escaping (timeout/memory kills, network + filesystem blocked, parent env not leaked), gate all execution with the kill switch, and inject a scoped secret that never leaks into output. No agent code yet.

---

## Phase 1 — Rust Core + Persistence (AthenaDB) ✅ COMPLETE

The vector engine. Built for speed, but with a durability story this time.

> **Now a standalone project.** AthenaDB has been extracted to its own repo
> (`../athenadb`) and is developed/released independently. Athena depends on it
> as an external package (built into the venv via `maturin develop --release`).
> Further DB enhancements (ANN index, group-commit WAL, HTTP endpoints) happen
> in that repo, not here.

### 1.1 Vector Math Core (`athenadb/src/core.rs`)

- [x] `Entry { id: String, vector: Vec<f32>, metadata: Value, namespace, embed_model_id, inv_norm }` + `VectorStore` with an id→pos index for O(1) upsert/delete.
- [x] `upsert`, `remove`, and `search(query, k, namespace?, embed_model_id?)` with namespace + embedding-model filtering baked in.
- [x] Cosine similarity, SIMD via `wide::f32x8` (precomputed `inv_norm`, so search is dot-product + 1 mul).
- [x] Parallel scan via `rayon::par_iter` with bounded per-thread min-heaps for top-k.
- [x] Benchmark: **1M vectors @ 768d, mean top-10 query = 40ms** (< 50ms target) on M-series Mac. (`tests/bench.rs`, ignored)

### 1.2 Persistence (`athenadb/src/wal.rs`, `snapshot.rs`)

- [x] Append-only WAL: length-prefixed bincode frames, fsync'd **before** in-memory mutation; dim validated before the WAL write so bad calls never pollute the log.
- [x] Snapshot: store serialized via `bincode`, written atomically (temp + fsync + rename); auto-triggered on a configurable interval (default 10k ops).
- [x] Recovery: on boot, load latest snapshot then replay WAL tail.
- [x] WAL compaction (truncate) after snapshot.
- [x] Test: torn WAL tail (kill -9 mid-write signature) ignored on replay; reopen recovers; snapshot+post-snapshot ops recover. (`tests/persistence.rs`, 6 passing)

### 1.3 PyO3 Bindings (`athenadb/src/python.rs`)

- [x] `AthenaDB.add(ids, vectors, metadatas, namespace, embed_model_id)`, `.query(vector, k, ...)`, `.delete(ids)`, `.snapshot()`, `__len__`. Metadata crosses the boundary as JSON strings (dependency-free).
- [x] Compatibility shim methods: `add_documents`, `query` (for `MemoryManager`).
- [x] Compile to `.so` via `maturin develop --release --features python`; feature-gated so the lib/bin build without PyO3. (`tests/test_athenadb.py`, 7 passing)

### 1.4 Axum HTTP Server (`athenadb/src/bin/server.rs`)

- [x] Scaffold only; routes return `501 Not Implemented` (verified via curl). Feature-gated behind `--features server`. Wired up in Phase 5 when multi-service need is real.

**Phase 1 exit criteria — ✅ MET:** `import athenadb` works; vectors written, process dropped, reopened, vectors still there (incl. torn-write recovery); 1M-vector search under the latency target; dual-mode (PyO3 + Axum) both build from one core.

---

## Phase 2 — Memory + Retrieval ✅ COMPLETE

Storage is easy. *Retrieval policy* is what makes the brain smart.

### 2.1 Tri-Partite Memory (`src/memory/`)

- [x] **Embedding seam** (`embedding.py`) — `Embedder` interface + deterministic, dependency-free `HashingEmbedder` default (offline-testable). Real backends (OpenAI/sentence-transformers) drop in behind the same interface; `embed_model_id` tags every vector.
- [x] `semantic.py` — facts/configs/context; `add_fact`, similarity-ranked.
- [x] `episodic.py` — task traces. Schema `{task_id, goal, plan, steps[], outcome, success, cost_tokens, duration_ms, agent_signatures[]}` via `log(...)`.
- [x] `procedural.py` — skill library. Schema `{skill_id, name, code, caps, tests, version, success_rate, parent_skill_id, status}` via `add_skill(...)`.
- [x] Each layer is a logical namespace (`{tenant}:{layer}`) inside one shared AthenaDB — partitioned by both tenant and layer at the engine level.
- [x] **Schema version** stamped on every record (`schema_version`) — the forward-migration invariant.

### 2.2 Retrieval Policy (`src/memory/retriever.py`)

- [x] Token-budgeted retrieval: caller specifies `max_tokens`; retriever packs by score until budget hit.
- [x] Recency decay: score `= similarity * exp(-age_days / half_life)`.
- [x] Reranker stage (optional, behind flag): `Reranker` interface + `IdentityReranker` passthrough (cross-encoder backend is future work).
- [x] Per-layer policies: episodic favors recency (half-life 14d), procedural favors success_rate, semantic favors similarity only.

### 2.3 Memory Hygiene

- [x] **Dedup on insert:** cosine ≥ 0.95 to an existing entry merges metadata instead of inserting a duplicate. All layers.
- [x] **Episode compression:** `EpisodicMemory.compress(hits, summarizer)` folds episodes into one "lessons" record and archives the originals (summarizer pluggable — LLM in prod, any callable in tests).
- [x] **Forgetting:** `archive(hit)` / `restore(hit)` move records to/from a `:archive` namespace — reversible, never destroyed. Live searches skip archived records.
- [ ] **Deferred — automated hygiene triggers:** scanning a namespace for "episodes older than N days" or "low-relevance for K retrievals" needs an AthenaDB `scan(namespace)` API the DB doesn't expose yet. The *mechanisms* (compress/archive) are done and tested; auto-triggering them is blocked on that DB enhancement (tracked in the AthenaDB repo).

**Phase 2 exit criteria — ✅ MET (15 tests):** retriever returns relevant memories within a token budget; duplicate facts collapse; episodes compress into lessons; layers are namespace-isolated; memory survives reopen; recency/success policies rank correctly.

---

## Phase 3 — Agents, ReAct Runtime & Cryptographic Ledger

The cognitive layer, now built on signed actions instead of hash-chained payloads.

### 3.0 LLM Gateway Seam (`src/llm/gateway.py`) — ✅ COMPLETE

- [x] `LLMClient` interface; all model access behind it. `Message`/`LLMResponse` types.
- [x] `ScriptedLLM` — deterministic, offline (responses list or handler) so the whole ReAct loop is testable without API keys.
- [x] `AnthropicClient` — real backend (lazy-imported `anthropic`), system-prompt caching; never touched by tests. Multi-model routing/fallback slot in here later.

### 3.1 BaseAgent (`src/agents/base.py`) — ✅ COMPLETE

- [x] Each agent loads its keypair on boot; `agent_id` = base58(public_key).
- [x] Every emitted action (THINK / CALL_SKILL / OBSERVATION / FINISH) is signed onto the ledger via `Ledger.append(identity, ...)`.
- [x] ReAct loop: `think → act → observe` with a hard iteration cap.
- [x] Honors the kill switch (halted → short-circuits before any LLM call; dry_run handled by the sandbox).
- [x] **Durable/resumable execution** — checkpoints state to disk after every step; `resume=True` continues from the last committed step.
- [x] **Reproducibility envelope** — records model_id, temperature, seed, and per-step prompt hashes.
- [ ] Accept handoffs only with a valid capability token issued to this agent — *deferred to 3.2 (needs multiple agents).*  Tests: `tests/test_agent.py` (9), `tests/test_llm.py` (6).

### 3.2 The Swarm

- [ ] `router.py` — decomposes a directive into a DAG of subtasks (planner), assigns to specialists. Returns a signed plan.
- [ ] `specialists/` — `coder.py`, `researcher.py`. Differentiated by system prompt and which memory partitions they query.
- [ ] `reflector.py` — replaces the bare "Evaluator". Reads the trace, can *reject and retry* (not just log). Decides whether to synthesize a new skill.
- [ ] `executor.py` — drives sandbox calls via Phase 0 sandbox.

### 3.3 ReAct Protocols

- [x] `CALL_SKILL { skill_id, args }` — pulls skill (from procedural memory or supplied set), runs in the Phase 0 sandbox under declared caps, folds the result back as an observation.
- [x] `EMIT_OBSERVATION` — observations are appended to the scratchpad and signed to the ledger.
- [x] Implemented actions are logged to the ledger as signed blocks; `finish` ends the loop.
- [ ] `CALL_AGENT { agent_id, capability_token, payload }` — protocol defined (parser + ledger action), receiver-side token verification wired in 3.2.

### 3.4 Cryptographic Swarm Ledger — ✅ COMPLETE

Signed, hash-chained blocks. **The whole ledger core is a native Rust crate
(`native/athena_ledger`, PyO3)** — block assembly, canonicalization, Ed25519
signing, SHA-256 hashing, chain verification, and JSONL persistence. The hot
path (auditing a long chain) runs entirely native; `src/core/ledger.py` is a
thin Python wrapper adding the agent-facing API + rotation-aware checks.

- [x] `Block { index, timestamp, agent_id, signing_pubkey, action_type, payload, prev_hash, signature, hash }` (native).
- [x] `signature` = Ed25519 over the canonical bytes of the block content; `hash` = SHA-256 of the same. Canonicalization lives in Rust (no Python↔Rust coupling).
- [x] `verify()` — native walk of the whole chain: index, content hash, prev-hash linkage, and signature per block. Returns `(ok, first_bad_index, reason)`.
- [x] Public key registry — reuses `identity.KeyRegistry`; `verify(registry=...)` adds rotation-aware validation that each block's signing key was valid for its agent at the block's timestamp.
- [x] Cross-language interop verified: a block signed in Rust verifies under Python `cryptography` and vice versa (standard Ed25519). 12 Python + 14 Rust tests.
- [ ] **Capability grants on the ledger** as a distinct action type (`Action.GRANT/REVOKE` defined; wired into the swarm in 3.2/3.3).
- [ ] **External anchoring (optional, behind flag):** every N blocks, post the Merkle root to an RFC 3161 timestamp service. *(Deferred — additive.)*

### 3.5 MCP Integration

- [ ] `src/agents/mcp_client.py` — agents can call any registered MCP tool as if it were a skill.
- [ ] MCP tool invocations are also signed and logged.

**Phase 3 exit criteria:** a router decomposes "research X and write a report", delegates to specialists with signed capability tokens, every step is on the ledger, the ledger verifies cleanly, and a tampered block is detected by `verify_chain()`.

---

## Phase 4 — Skills: Curation & Evaluation

This is what most "agent platforms" never build. Without it, the skill library degenerates into junk within a week.

### 4.1 Skill Synthesis Pipeline (`src/skills/synthesize.py`)

When the Reflector decides a task needed a new skill:

1. **Generate** — LLM proposes `{name, docstring, code, declared_caps}`.
2. **Generate tests** — same LLM, separate call: synthesize 3–5 unit tests for the skill against the original task.
3. **Sandbox-run tests** — execute in Phase 0 sandbox with declared caps.
4. **Quarantine** — if all tests pass, store in procedural memory with `status: quarantined`, `success_count: 0`.
5. **Promote** — after K successful real uses (default K=3), flip to `status: promoted`.
6. **Deprecate** — failure rate above threshold flips back to quarantined or `deprecated`.

### 4.2 Skill Curation

- [ ] **Dedup:** before insert, embed `name + docstring` and check procedural memory for similarity > 0.9. If found, the new skill becomes a *version* of the existing one, not a new entry.
- [ ] **Versioning:** `skill_id` is stable; versions chain via `parent_skill_id`. Retrieval prefers latest promoted version.
- [ ] **Cap enforcement:** at synthesis time, statically reject skills whose code uses imports outside declared caps (AST walk).

### 4.3 Evaluation Harness (`src/eval/`)

- [ ] `bench/` — directory of `{task.yaml, expected.json}` pairs. Tasks span coding, retrieval, multi-step reasoning.
- [ ] `harness.py` — runs full suite, scores per-task, aggregates: success rate, mean tokens, mean latency, mean cost.
- [ ] **Regression mode:** when a new skill is promoted, re-run benchmarks that previously failed *without* this skill. Records lift.
- [ ] Output: `eval/runs/<timestamp>/report.html` with deltas vs. last run.
- [ ] CI hook: any PR that touches `src/agents/` or `src/skills/` runs the harness before merge.

**Phase 4 exit criteria:** swarm solves a benchmark task, Reflector synthesizes a skill with tests, skill is quarantined, three subsequent task runs promote it, harness shows positive lift vs. baseline.

---

## Phase 5 — UI, Observability & Platform Polish

### 5.1 React Dashboard (`frontend/`)

- [ ] Vite + React + Tailwind, dark monospace aesthetic.
- [ ] **Task Console** — dispatch directives, see plan DAG render live.
- [ ] **Swarm Feed** — collapsible per-agent traces, signature & ledger hash on each card.
- [ ] **Chain Auditor** — visualize blocks, verify signatures, surface tampering.
- [ ] **Skill Library Browser** — table of skills with version, status, success rate, recent usage. Filter by capability.
- [ ] **Eval Dashboard** — bench score trend, cost-per-task trend, regression alerts.

### 5.2 Backend (`src/core/api.py`)

- [ ] FastAPI + WebSockets. Streams ledger blocks to UI as they're written.
- [ ] REST endpoints for skill list, eval reports, kill-switch toggle.
- [ ] Auth: HMAC on every request (use a separate platform key — agents have keypairs, the dashboard has a shared secret).

### 5.3 Observability

- [ ] **Prometheus metrics:** `swarm_tasks_total{outcome}`, `swarm_task_duration_seconds`, `skill_invocations_total{skill_id,outcome}`, `llm_tokens_total{model,direction}`, `llm_cost_usd_total`.
- [ ] **OpenTelemetry traces:** one span per agent step, one span per skill invocation, one root span per task. Attributes include `agent_id`, `block_hash`.
- [ ] **Structured logs:** JSON to stdout, fields include `task_id`, `agent_id`, `block_index`.

### 5.4 AthenaDB HTTP Mode (defer-or-commit decision lives here)

- [ ] If multi-service use case has emerged: wire up the Axum endpoints from Phase 1.4, expose `/add`, `/query`, `/snapshot`.
- [ ] Otherwise delete `bin/server.rs` — don't carry dead optionality.

**Phase 5 exit criteria:** non-technical user can dispatch a task, watch the swarm execute, audit the ledger, see metrics in Grafana, and the platform doesn't go down when AthenaDB restarts.

---

## What's Explicitly *Not* in Scope

To avoid feature creep, these are out unless a concrete need appears:

- Multi-tenant isolation (single-org platform until proven otherwise).
- Distributed AthenaDB replication.
- Fine-tuning custom models — Athena uses off-the-shelf Claude.
- Computer-use / browser-control skills (revisit after Phase 4).
- A blockchain consensus protocol — Athena uses signed actions + optional external anchoring; consensus is not needed for a single-org swarm.

---

## Sequencing Notes

- **Phase 0 must complete before any agent code.** Identity and sandbox are load-bearing for every later phase.
- **Phases 1 and 2 can interleave** (Rust core in parallel with retrieval policy design).
- **Phase 3 is the longest** — budget 2x any other phase.
- **Phase 4 unblocks the "self-improving" claim.** Until then it's a fancy ReAct system.
- **Phase 5 is mostly polish**, but Prometheus + OTel come earlier in practice (wire them in during Phase 3).
