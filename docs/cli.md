# CLI reference

The `athena` command drives everything the dashboard can do. It talks to the running
server over HTTP, so it works locally or against a remote instance (`--host` / `--port`).

Run `athena --help`, or `athena <command> --help`, for the authoritative list.

## Server

| Command | Does |
|---|---|
| `athena up [--foreground] [--open]` | Start the server as a background daemon |
| `athena down` | Stop the daemon |
| `athena restart` | Stop, wait for the port to free, start again |
| `athena rebuild [--no-build]` | Rebuild the dashboard, then restart |
| `athena status` | Model, safety, ledger size, capabilities, cache |
| `athena serve` | Run in the foreground |
| `athena open` | Open the dashboard in a browser |
| `athena desktop [--build]` | Launch the native desktop app |

## Driving the swarm

| Command | Does |
|---|---|
| `athena run "…"` | Dispatch a directive; streams the run live |
| `athena run "…" --json` | Machine-readable result (for scripts) |
| `athena chat` | Interactive terminal session |
| `athena search "…"` | Search the web via the agent's tools |
| `athena remember "…" [--layer]` | Store a fact in memory |
| `athena memory <layer> [query]` | Browse semantic / episodic / procedural memory |

Directives can also be piped: `echo "summarize this" | athena run`.

## Trust and performance

| Command | Does |
|---|---|
| `athena verify` | Verify the signed ledger chain |
| `athena metrics` | Tasks, tokens, cost, skills synthesized |
| `athena eval` | Run the benchmark suite |
| `athena agents` | The swarm's signed agent identities |

## Skills

| Command | Does |
|---|---|
| `athena skills` | List learned skills (📌 marks promoted permanent tools) |
| `athena skills synth "…"` | Synthesize a new skill |
| `athena skills approve <id>` | Approve a pending skill (gated mode) |
| `athena skills reject <id>` | Reject it |

## Capabilities

| Command | Does |
|---|---|
| `athena workspace [on\|off]` | The jailed file workspace; lists files + tools |
| `athena playbooks [list\|add\|rm\|on\|off]` | Authored markdown procedures |
| `athena subagents [list\|add\|rm]` | Custom specialists in the router's roster |
| `athena cache [status\|on\|off\|clear]` | Semantic answer cache |
| `athena personas [list\|add\|rm]` | Saved system prompts |
| `athena recipes [list\|add\|rm]` | Saved task templates |

Examples:

```bash
athena playbooks add "Deploy checklist" --desc "ship safely" --body "1. run tests…"
athena subagents add "Legal reviewer" --prompt "You review contracts…" --iters 6
```

## Self-evolving harness

| Command | Does |
|---|---|
| `athena evolution` | Routing accuracy, learned config, pinned tools, retired roles |
| `athena evolve` | Run one evolution pass (all operators, each gated) |
| `athena evolution revert` | Roll back the most recent change |
| `athena evolution auto on --every 20` | Evolve automatically every N episodes |
| `athena evolution unpin <skill_id>` | Un-promote a permanent tool |
| `athena evolution unretire <role>` | Bring a retired specialist back |

## Safety

| Command | Does |
|---|---|
| `athena safety [live\|dry-run\|halted]` | The kill switch |
| `athena approval [auto\|gated]` | Whether a human approves synthesized skills |

## Models and account

| Command | Does |
|---|---|
| `athena models [--set BACKEND[:MODEL]]` | Show or switch the LLM |
| `athena login` / `logout` / `whoami` | Account session |
| `athena messaging` | Messaging gateways (admin) |
| `athena version` | Version |
