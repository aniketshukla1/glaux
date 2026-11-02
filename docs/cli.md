# CLI reference

The `glaux` command drives everything the dashboard can do. It talks to the running
server over HTTP, so it works locally or against a remote instance (`--host` / `--port`).

Run `glaux --help`, or `glaux <command> --help`, for the authoritative list.

## Server

| Command | Does |
|---|---|
| `glaux up [--foreground] [--open]` | Start the server as a background daemon |
| `glaux down` | Stop the daemon |
| `glaux restart` | Stop, wait for the port to free, start again |
| `glaux rebuild [--no-build]` | Rebuild the dashboard, then restart |
| `glaux status` | Model, safety, ledger size, capabilities, cache |
| `glaux serve` | Run in the foreground |
| `glaux open` | Open the dashboard in a browser |
| `glaux desktop [--build]` | Launch the native desktop app |

## Driving the swarm

| Command | Does |
|---|---|
| `glaux run "…"` | Dispatch a directive; streams the run live |
| `glaux run "…" --json` | Machine-readable result (for scripts) |
| `glaux chat` | Interactive terminal session |
| `glaux search "…"` | Search the web via the agent's tools |
| `glaux remember "…" [--layer]` | Store a fact in memory |
| `glaux memory <layer> [query]` | Browse semantic / episodic / procedural memory |

Directives can also be piped: `echo "summarize this" | glaux run`.

## Trust and performance

| Command | Does |
|---|---|
| `glaux verify` | Verify the signed ledger chain |
| `glaux verify --file PATH` | Verify a ledger offline — no server, no trust in the app |
| `glaux metrics` | Tasks, tokens, cost, skills synthesized |
| `glaux eval` | Run the benchmark suite |
| `glaux agents` | The swarm's signed agent identities |

## Skills

| Command | Does |
|---|---|
| `glaux skills` | List learned skills (📌 marks promoted permanent tools) |
| `glaux skills synth "…"` | Synthesize a new skill |
| `glaux skills approve <id>` | Approve a pending skill (gated mode) |
| `glaux skills reject <id>` | Reject it |

## Capabilities

| Command | Does |
|---|---|
| `glaux workspace [on\|off]` | The jailed file workspace; lists files + tools |
| `glaux playbooks [list\|add\|rm\|on\|off]` | Authored markdown procedures |
| `glaux subagents [list\|add\|rm]` | Custom specialists in the router's roster |
| `glaux cache [status\|on\|off\|clear]` | Semantic answer cache |
| `glaux personas [list\|add\|rm]` | Saved system prompts |
| `glaux recipes [list\|add\|rm]` | Saved task templates |

Examples:

```bash
glaux playbooks add "Deploy checklist" --desc "ship safely" --body "1. run tests…"
glaux subagents add "Legal reviewer" --prompt "You review contracts…" --iters 6
```

## Self-evolving harness

| Command | Does |
|---|---|
| `glaux evolution` | Routing accuracy, learned config, pinned tools, retired roles |
| `glaux evolve` | Run one evolution pass (all operators, each gated) |
| `glaux evolution revert` | Roll back the most recent change |
| `glaux evolution auto on --every 20` | Evolve automatically every N episodes |
| `glaux evolution unpin <skill_id>` | Un-promote a permanent tool |
| `glaux evolution unretire <role>` | Bring a retired specialist back |

## Safety

| Command | Does |
|---|---|
| `glaux safety [live\|dry-run\|halted]` | The kill switch |
| `glaux approval [auto\|gated]` | Whether a human approves synthesized skills |

## Models and account

| Command | Does |
|---|---|
| `glaux models [--set BACKEND[:MODEL]]` | Show or switch the LLM |
| `glaux login` / `logout` / `whoami` | Account session |
| `glaux messaging` | Messaging gateways (admin) |
| `glaux version` | Version |
