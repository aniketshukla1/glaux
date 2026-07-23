# HTTP API

The server exposes a JSON API on `http://127.0.0.1:8000` by default. This surface —
together with the `athena` CLI — is what Athena's [semantic version](https://semver.org/)
promise covers.

Set `ATHENA_API_SECRET` to require signed requests. Most endpoints require an
authenticated session; `/api/health` is public.

## Running tasks

### `POST /api/task`
Run a directive and wait for the result.

```bash
curl -X POST localhost:8000/api/task \
  -H 'Content-Type: application/json' \
  -d '{"directive": "explain bloom filters"}'
```

Returns `success`, `final`, `cost`, `model`, `plan`, `steps`, `new_blocks`,
`verification`, `session_id`. A cache hit additionally returns `cached: true`,
`similarity`, and `matched_directive`.

### `POST /api/task/stream`
Same, as Server-Sent Events: a `start` event, live `block` events (each signed step),
`token` deltas as the answer streams, then `done` with the full result.

### `POST /api/task/stop`
Cancel the running task for the current user.

## Trust

| Endpoint | Does |
|---|---|
| `GET /api/health` | Status, model, safety, ledger size, capabilities *(public)* |
| `GET /api/ledger` | Blocks + chain verification |
| `GET /api/agents` | Agent identities and public keys |
| `GET /api/metrics` | Task, token, and cost counters |

## Skills

| Endpoint | Does |
|---|---|
| `GET /api/skills[?status=]` | List skills |
| `POST /api/skills/synthesize` | Synthesize a skill (`{task}`) |
| `POST /api/skills/{id}/approve` · `/reject` | Gated-mode approval |
| `POST /api/skills/{id}/use` | Record a use (`{success}`) |

## Capabilities

| Endpoint | Does |
|---|---|
| `GET/POST /api/fs` | Jailed workspace: state, files, tools; `{enabled}` toggles |
| `GET/POST /api/playbooks` · `DELETE /api/playbooks/{slug}` | Authored playbooks |
| `POST /api/playbooks/enabled` | Expose playbooks to the swarm |
| `GET/POST /api/subagents` · `DELETE /api/subagents/{slug}` | Custom specialists |
| `GET/POST/DELETE /api/cache` | Semantic answer cache: stats, toggle, clear |

## Self-evolving harness

| Endpoint | Does |
|---|---|
| `GET /api/evolution` | Accuracy, learned config, pinned tools, retired roles, log |
| `POST /api/evolution/evolve` | Run every operator (each independently gated) |
| `POST /api/evolution/revert` | Roll back the last change |
| `POST /api/evolution/auto` | `{enabled, every}` cadence |
| `POST /api/evolution/unpin/{skill_id}` | Un-promote a permanent tool |
| `POST /api/evolution/unretire/{role}` | Restore a retired specialist |

## Controls

| Endpoint | Does |
|---|---|
| `GET/POST /api/safety` | Kill switch: `live` · `dry_run` · `halted` |
| `GET/POST /api/approval` | `auto` · `gated` |
| `GET/POST /api/llm` | Show or switch the model backend |
| `GET /api/memory/{layer}` · `POST` | Browse or add memory |
| `GET /api/workspace` | Projects, sessions, personas, recipes |
| `POST /api/mcp/call` | Call an MCP tool (`{tool, args}`) |

## Errors

Standard HTTP codes with a JSON `{"detail": "..."}` body: `400` invalid input, `401`
not signed in, `403` admin required, `404` unknown resource, `413` directive too long,
`502` the model backend failed.
