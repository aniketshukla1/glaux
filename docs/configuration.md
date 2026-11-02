# Configuration

## Models

Glaux runs offline by default. Switch backends at runtime — no restart:

```bash
glaux models                                   # current + available
glaux models --set ollama:qwen2.5:7b-instruct  # fully local
glaux models --set anthropic                   # needs ANTHROPIC_API_KEY
glaux models --set openai                      # needs OPENAI_API_KEY
```

30+ providers are supported. API keys are read from the environment and are never
written to the ledger or logs.

**Model tiering.** Routing and reflection can use a cheaper model than the specialists
that do the real work — set a fast model via `POST /api/llm/fast` or the dashboard.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GLAUX_HOME` | `~/.glaux` | State directory: ledger, memory, skills, workspace, logs |
| `GLAUX_API_SECRET` | — | Require signed requests on the HTTP API |
| `GLAUX_WORKSPACE` | off | Seed the jailed file workspace as enabled |
| `GLAUX_PLAYBOOKS` | off | Seed authored playbooks as exposed to the swarm |
| `GLAUX_ANSWER_CACHE` | `0` (off) | Enable the semantic answer cache |
| `GLAUX_CACHE_THRESHOLD` | `0.92` | Similarity required for a cache hit |
| `GLAUX_CACHE_MAX` | `500` | Max cached answers |
| `GLAUX_CONTEXT_MAX_CHARS` | `6000` | History budget per prompt on long runs |
| `GLAUX_CONTEXT_KEEP_RECENT` | `3` | Steps kept verbatim before digesting |
| `GLAUX_SANDBOX_BACKEND` | `auto` | `wasm` or `subprocess` |
| `GLAUX_PYTHON_WASM` | — | Path to `python.wasm` for the WASM sandbox |
| `GLAUX_ANTHROPIC_CACHE_TTL` | — | Set `1h` for the extended prompt cache |

Each variable also answers to its pre-rename `ATHENA_*` name (the `GLAUX_*` one wins
when both are set), and an existing `~/.athena` keeps being used while there is no
`~/.glaux`.

Runtime toggles (`glaux workspace on`, `glaux cache on`, …) override the env seed and
persist, so the env vars are only about the starting state.

## Capabilities

Glaux ships conservative — each capability is opt-in:

| Capability | Enable | What it grants |
|---|---|---|
| Workspace | `glaux workspace on` | Real files in one jailed, size-capped directory |
| Playbooks | `glaux playbooks on` | The swarm can list and follow authored procedures |
| Answer cache | `glaux cache on` | Near-identical repeats answered with zero model calls |
| Auto-evolve | `glaux evolution auto on` | The harness improves itself on a cadence |

## Safety controls

```bash
glaux safety live       # normal
glaux safety dry-run    # skip side effects
glaux safety halted     # stop all execution
glaux approval gated    # a human approves each synthesized skill before it can run
```

## Budgets

Each task runs under a budget (model calls, tokens, spend). The swarm halts cleanly
when a limit is hit rather than running away — the halt reason is returned with the
result and recorded.

## Context management

Long runs compact their own history: recent steps stay verbatim, older ones collapse to
one-line digests, and the deepest history is elided — all under
`GLAUX_CONTEXT_MAX_CHARS`. Every compaction is signed to the ledger, so nothing
silently disappears from the record.
