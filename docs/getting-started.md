# Getting started

## Requirements

- **Python 3.10+**
- **A Rust toolchain** — the ledger kernel is a native crate built during install ([rustup.rs](https://rustup.rs))
- **Node.js 18+** — to build the dashboard
- *Optional:* [AthenaDB](https://github.com/aniketshukla/athenadb) cloned as a sibling directory, for the memory layers

## Install

```bash
git clone https://github.com/aniketshukla/athena-agent && cd athena-agent
./install.sh
```

`install.sh` creates a virtualenv, installs dependencies, builds the native ledger
kernel with maturin, installs the `athena` command, and builds the dashboard.

## First run

```bash
./venv/bin/athena up          # starts the server → http://127.0.0.1:8000
```

Open the dashboard, create an account (the first account is yours), and give it a goal.
Or stay in the terminal:

```bash
athena run "explain how a bloom filter works"
athena chat                    # interactive session
```

Athena works offline out of the box using the bundled demo backend. For real work,
point it at a model:

```bash
athena models                                   # what's available
athena models --set ollama:qwen2.5:7b-instruct  # fully local
athena models --set anthropic                   # needs ANTHROPIC_API_KEY
```

## Prove it worked

Every step the swarm took was signed. Verify the chain:

```bash
athena verify
# ✓ chain verified   ·   1,382 signed blocks
```

## Turn on the capabilities you want

Athena ships conservative. Enable what you need:

```bash
athena workspace on     # let agents create real files in a jailed directory
athena playbooks on     # expose authored playbooks to the swarm
athena cache on         # semantic answer cache (skips repeat work)
```

## Useful next steps

```bash
athena status           # model, safety, ledger size, capabilities
athena skills           # what it has learned to do
athena evolution        # how it has improved its own routing
athena --help           # everything
```

## Where things live

State lives in `ATHENA_HOME` (default `~/.athena`): the ledger, memory, skills,
workspace, playbooks, and logs. Delete it to start clean.

## Next

- [Configuration](configuration.md) — models, environment variables, capabilities
- [CLI reference](cli.md) — every command
- [Architecture](architecture.md) — how the swarm actually works
- [Security model](security.md) — the sandbox, the jail, and the trade-offs
