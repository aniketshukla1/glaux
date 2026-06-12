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
| LLM provider         | Pluggable behind `LLMClient`: Anthropic SDK, **Ollama (local)**, or offline DemoLLM | Anthropic for quality; Ollama to benchmark/test on a real local model with zero cost; Demo for offline. Switchable at runtime via `/api/llm` + a header selector. |
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
- [x] **Cost/budget guard** (Phase 3) — one `BudgetTracker` shared across router/specialists/reflector; the agent loop checks `max_tokens` / `max_usd` / `max_llm_calls` before each LLM call and the swarm stops dispatching when exceeded, halting the task cleanly. Surfaced in the UI (budget inputs + cost meter + halt banner). `src/agents/budget.py`; tests `tests/test_budget.py` (8) + API.
- [x] **HITL approval gate** (Phase 3) — autonomously synthesized skills that are *sensitive* (net / fs_write / secrets) or produced under **gated** approval mode land as `pending_approval` and cannot run until a human approves them (`SkillLibrary.approve`/`reject`); `REQUEST_APPROVAL` is logged to the ledger. UI: approval-mode toggle + Approve/Reject in the Skills tab.

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

### 3.2 The Swarm — ✅ COMPLETE

- [x] `router.py` — decomposes a directive into a DAG of subtasks (`Step`s with `depends_on`), assigns roles. Returns a plan signed onto the ledger (`Action.PLAN`).
- [x] `specialists.py` — `coder_agent` / `researcher_agent` factories: `BaseAgent`s differentiated by role system prompt. *(Memory-partition routing — researchers leaning on semantic memory — is a noted refinement.)*
- [x] `reflector.py` — reviews a result and returns accept/retry; the swarm re-runs a step with the critique in context (reject-and-retry, not just log). Skill-synthesis-on-reflection lands in Phase 4.
- [x] `swarm.py` — orchestrator: router → topological execution → token-gated `delegate` per step → reflect/retry → thread dependency outputs into context. Executor role is the existing `BaseAgent` sandbox path.
- [x] `handoff.py` — `delegate()` mints a signed capability token, logs `CALL_AGENT` + `CAPABILITY_GRANT`, and the receiver's `accept_handoff` verifies it before working. Tests: `tests/test_swarm.py` (11) incl. rejection of mis-addressed / expired / tampered tokens.

> [!NOTE]
> **Known gap (flagged, not claimed done):** specialists are differentiated by *prompt only*, not yet by **memory partition**. The ReAct loop currently retrieves *procedural* skills into context but does not pull **semantic/episodic** memory — so e.g. a researcher does not yet lean on semantic facts. This is a deliberate refinement deferred to a later pass (wire `MemoryManager.semantic`/`episodic` retrieval into `BaseAgent._build_messages`, and add `retrieved_memory_hash` to the reproducibility envelope at the same time).

### 3.3 ReAct Protocols

- [x] `CALL_SKILL { skill_id, args }` — pulls skill (from procedural memory or supplied set), runs in the Phase 0 sandbox under declared caps, folds the result back as an observation.
- [x] `EMIT_OBSERVATION` — observations are appended to the scratchpad and signed to the ledger.
- [x] Implemented actions are logged to the ledger as signed blocks; `finish` ends the loop.
- [x] `CALL_AGENT { agent_id, capability_token }` — token-gated handoff via `delegate` / `accept_handoff`; receiver verifies the token (subject + capability + expiry + signature) before accepting. Mis-addressed, expired, and tampered tokens are all rejected. Logged as signed `CALL_AGENT` + `CAPABILITY_GRANT` blocks.

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

### 3.5 MCP Integration — ✅ COMPLETE

- [x] `src/agents/mcp.py` — `MCPClient` interface + `LocalMCPClient` (real in-process tools: `calc`, `word_count`, `uppercase`). Agents call tools via the `call_mcp` action; tools are listed in the prompt alongside skills.
- [x] MCP tool invocations are signed + logged as `MCP_TOOL` ledger blocks; honor the kill switch (skipped in dry-run).
- [x] API: `GET /api/mcp/tools`, `POST /api/mcp/call`. Frontend: **MCP tab** — list tools, call one with JSON args, see the result.
- [ ] Real stdio/HTTP MCP servers behind the same interface (via the `mcp` SDK) — *extension point; the integration layer is done.* Tests: `tests/test_mcp.py` (9) + API.

**Phase 3 exit criteria:** a router decomposes "research X and write a report", delegates to specialists with signed capability tokens, every step is on the ledger, the ledger verifies cleanly, and a tampered block is detected by `verify_chain()`.

---

## Phase 4 — Skills: Curation & Evaluation

This is what most "agent platforms" never build. Without it, the skill library degenerates into junk within a week.

### 4.1 Skill Synthesis Pipeline (`src/skills/synthesize.py`) — ✅ COMPLETE

- [x] **Generate** — LLM proposes `{name, description, code, entrypoint, caps, tests}` in one structured call (`SkillSynthesizer`).
- [x] **Sandbox-run tests** — each test runs in the Phase 0 sandbox under the skill's declared caps; all must pass.
- [x] **Quarantine** — passing skills enter procedural memory with `status: quarantined`, counters at 0 (`SkillLibrary.add_candidate`).
- [x] **Promote** — after K successful uses (default 3) via `record_use`, flips to `promoted`.
- [x] **Deprecate** — once `usage_count ≥ min_uses` and `success_rate < threshold`, flips to `deprecated`.
- [x] **Reflector-triggered synthesis** — the reflector can recommend a reusable skill (`Verdict.synthesize`); the swarm runs the full synthesis pipeline, applies the HITL gate, and logs `SYNTHESIZE_SKILL` (+ `REQUEST_APPROVAL` when gated) to the ledger. The autonomous self-improvement loop is closed: dispatch → reflect → synthesize → (approve) → benchmark lift.

### 4.2 Skill Curation — ✅ COMPLETE

- [x] **Versioning:** near-duplicate (`name + description` cosine ≥ 0.9) becomes a new *version* linked by `parent_skill_id`, not a sibling.
- [x] **Cap enforcement:** AST `static_cap_check` rejects, at synthesis time, code with network imports without `net`, process/FFI escapes, or `open(...,'w')` without `fs_write`.
- [ ] Retrieval prefers latest promoted version — *refinement (current procedural policy already favors high success_rate).*

> **Frontend:** Skills tab — synthesize from a task, see cap-violations / test pass-count, and the library with status badge, version, success-rate, and record-success/failure controls. API: `GET /api/skills`, `POST /api/skills/synthesize`, `POST /api/skills/{id}/use`. Tests: `tests/test_skills.py` (13) + API (3).

### 4.3 Evaluation Harness (`src/eval/`) — ✅ COMPLETE

- [x] `bench/` — JSON cases (each: skill-by-name or inline code + args + expected + tags). Ship coding/edge/baseline cases.
- [x] `harness.py` — `EvalHarness` runs each case in the Phase 0 sandbox, scores exact-match pass/fail, records per-case latency; `EvalRun` aggregates pass rate.
- [x] **Lift mode:** `lift(current, previous)` reports newly-passing / regressed cases and Δ pass-rate — promoting a synthesized skill shows measurable improvement.
- [x] API: `POST /api/eval/run` (runs suite vs. current library, returns run + lift), `GET /api/eval/runs` (history). Tests: `tests/test_eval.py` (6) + API.
- [ ] HTML report file / CI hook — *the Eval Dashboard supersedes the static report; CI hook is future.*

> **Frontend:** Eval Dashboard tab — "Run benchmark", pass-rate, per-case ✓/✗ with expected-vs-got, lift badge (▲/▼ vs last), and pass-rate history. Verified live: 2/4 → synthesize → 4/4, ▲50%.

**Phase 4 exit criteria — ✅ MET (offline demo):** synthesize a skill with tests → quarantined → promotes after K uses; benchmark suite goes 50%→100% with the skill, and the harness reports the positive lift. *(Reflector-triggered autonomous synthesis is the remaining wiring.)*

---

## Phase 5 — UI, Observability & Platform Polish

> **Started early (in parallel)** so the swarm is viewable/testable while later phases land. First cut is live: dispatch a directive, watch the signed trace, audit the chain.

### 5.1 React Dashboard (`frontend/`) — 🟡 IN PROGRESS

- [x] Vite + React + Tailwind, dark glassmorphism aesthetic.
- [x] **Task Console** — dispatch directives; shows the returned plan DAG + result.
- [x] **Swarm Feed** — collapsible signed-action cards (action type, agent id, hash); expand for payload + Ed25519 signature.
- [x] **Chain Auditor** — verification banner (native Rust verify), block count, re-verify; surfaces the exact tampered block.
- [x] **Safety control** — header toggle for the kill switch (live / dry_run / halted), wired to `/api/safety`.
- [x] **Memory browser** — tabbed semantic/episodic/procedural with add + search (Phase 2 parity).
- [x] **Agent Roster** — agents with role, public key, namespace (Phase 0/3 identity parity).
- [ ] **Skill Library Browser** — needs Phase 4 (skills).
- [ ] **Eval Dashboard** — needs Phase 4 (eval harness).

> **Policy:** the frontend tracks the backend phase-for-phase from here on — each phase ships matching API + UI, and the UI stays at parity with built subsystems.

### 5.2 Backend (`src/core/api.py`) — 🟡 IN PROGRESS

- [x] FastAPI app: `POST /api/task` (run swarm), `GET /api/ledger`, `GET /api/block/{i}`, `GET /api/health`, `DELETE /api/ledger`. Persistent ledger + stable agent identities across dispatches. Offline `DemoLLM` by default; real Claude when `ANTHROPIC_API_KEY` is set.
- [x] **Safety** endpoints — `GET`/`POST /api/safety` (kill-switch toggle).
- [x] **Memory** endpoints — `GET`/`POST /api/memory/{layer}` (browse/search/add via AthenaDB `scan`), `DELETE /api/memory`.
- [x] **Roster** endpoint — `GET /api/agents`. Tests: `tests/test_api.py` (11).
- [ ] **WebSocket live streaming** — stream blocks as they're written (today the full signed trace renders on completion).
- [x] REST endpoints for skill list + eval reports (Phase 4).
- [x] **Auth: HMAC request signing** (`src/core/auth.py`) — env-gated by `ATHENA_API_SECRET`; every `/api/*` request signed with `X-Athena-Timestamp` + `X-Athena-Signature` (HMAC-SHA256 over `ts\nMETHOD\npath\nsha256(body)`), with a replay window and constant-time compare. `/api/health` + `/api/auth` stay public to bootstrap. The shared platform secret is separate from agent keypairs. Frontend signs via Web Crypto (`VITE_ATHENA_API_SECRET`). Tests: `tests/test_auth.py` (8). Verified live: unsigned → 401, signed dashboard works.

### 5.3 Observability — 🟡 IN PROGRESS

- [x] **Prometheus metrics** (`src/core/observability.py`, scrapeable at `/metrics`): `swarm_tasks_total{outcome}`, `swarm_task_duration_seconds_{sum,count}`, `llm_calls_total`, `llm_tokens_total`, `llm_cost_usd_total`, `skills_synthesized_total`, `eval_runs_total`, `eval_pass_rate`. Plus `/api/metrics` (JSON KPIs) and a **Metrics dashboard tab**.
- [x] **Structured logs:** one JSON line per task/eval to stdout (`log_json`).
- [ ] **OpenTelemetry traces** — one span per agent step / skill / task with `agent_id` + `block_hash`. *(Deferred — needs a collector to be useful.)*

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
