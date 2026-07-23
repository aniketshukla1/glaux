# Configuration

## Models

Athena runs offline by default. Switch backends at runtime — no restart:

```bash
athena models                                   # current + available
athena models --set ollama:qwen2.5:7b-instruct  # fully local
athena models --set anthropic                   # needs ANTHROPIC_API_KEY
athena models --set openai                      # needs OPENAI_API_KEY
```

30+ providers are supported. API keys are read from the environment and are never
written to the ledger or logs.

**Model tiering.** Routing and reflection can use a cheaper model than the specialists
that do the real work — set a fast model via `POST /api/llm/fast` or the dashboard.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ATHENA_HOME` | `~/.athena` | State directory: ledger, memory, skills, workspace, logs |
| `ATHENA_API_SECRET` | — | Require signed requests on the HTTP API |
| `ATHENA_WORKSPACE` | off | Seed the jailed file workspace as enabled |
| `ATHENA_PLAYBOOKS` | off | Seed authored playbooks as exposed to the swarm |
| `ATHENA_ANSWER_CACHE` | `0` (off) | Enable the semantic answer cache |
| `ATHENA_CACHE_THRESHOLD` | `0.92` | Similarity required for a cache hit |
| `ATHENA_CACHE_MAX` | `500` | Max cached answers |
| `ATHENA_CONTEXT_MAX_CHARS` | `6000` | History budget per prompt on long runs |
| `ATHENA_CONTEXT_KEEP_RECENT` | `3` | Steps kept verbatim before digesting |
| `ATHENA_SANDBOX_BACKEND` | `auto` | `wasm` or `subprocess` |
| `ATHENA_PYTHON_WASM` | — | Path to `python.wasm` for the WASM sandbox |
| `ATHENA_ANTHROPIC_CACHE_TTL` | — | Set `1h` for the extended prompt cache |

Runtime toggles (`athena workspace on`, `athena cache on`, …) override the env seed and
persist, so the env vars are only about the starting state.

## Capabilities

Athena ships conservative — each capability is opt-in:

| Capability | Enable | What it grants |
|---|---|---|
| Workspace | `athena workspace on` | Real files in one jailed, size-capped directory |
| Playbooks | `athena playbooks on` | The swarm can list and follow authored procedures |
| Answer cache | `athena cache on` | Near-identical repeats answered with zero model calls |
| Auto-evolve | `athena evolution auto on` | The harness improves itself on a cadence |

## Safety controls

```bash
athena safety live       # normal
athena safety dry-run    # skip side effects
athena safety halted     # stop all execution
athena approval gated    # a human approves each synthesized skill before it can run
```

## Budgets

Each task runs under a budget (model calls, tokens, spend). The swarm halts cleanly
when a limit is hit rather than running away — the halt reason is returned with the
result and recorded.

## Context management

Long runs compact their own history: recent steps stay verbatim, older ones collapse to
one-line digests, and the deepest history is elided — all under
`ATHENA_CONTEXT_MAX_CHARS`. Every compaction is signed to the ledger, so nothing
silently disappears from the record.
