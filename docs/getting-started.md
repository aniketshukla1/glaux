# Getting started

## Requirements

- **Python 3.10+**
- **A Rust toolchain** — the ledger kernel and vector store are native crates built during install ([rustup.rs](https://rustup.rs))
- **[AthenaDB](https://github.com/aniketshukla1/athenadb)**, cloned as a sibling directory —
  the memory layers and the skill library are built on it, so the server does not start
  without it. `install.sh` checks for it before doing any work.
- **Node.js 18+** — to build the dashboard. Ubuntu's default `nodejs` package is older
  than this; install a current Node with [nvm](https://github.com/nvm-sh/nvm) or
  [NodeSource](https://github.com/nodesource/distributions) if the dashboard is skipped.
  The API and CLI work without it.

## Install

Clone both repos side by side, then install from `glaux`:

```bash
git clone https://github.com/aniketshukla1/athenadb
git clone https://github.com/aniketshukla1/glaux && cd glaux
./install.sh
```

`install.sh` creates a virtualenv, installs dependencies, builds the native ledger
kernel with maturin, installs the `glaux` command, and builds the dashboard.

To check the whole path on a pristine machine — the exact thing a new user hits —
`scripts/clean_install_test.sh` runs it end to end in a clean container and verifies a
signed ledger at the other side.

## First run

```bash
./venv/bin/glaux up          # starts the server → http://127.0.0.1:8000
```

Open the dashboard, create an account (the first account is yours), and give it a goal.
Or stay in the terminal:

```bash
glaux run "explain how a bloom filter works"
glaux chat                    # interactive session
```

Glaux works offline out of the box using the bundled demo backend. For real work,
point it at a model:

```bash
glaux models                                   # what's available
glaux models --set ollama:qwen2.5:7b-instruct  # fully local
glaux models --set anthropic                   # needs ANTHROPIC_API_KEY
```

## Prove it worked

Every step the swarm took was signed. Verify the chain:

```bash
glaux verify
# ✓ chain verified   ·   1,382 signed blocks
```

## Turn on the capabilities you want

Glaux ships conservative. Enable what you need:

```bash
glaux workspace on     # let agents create real files in a jailed directory
glaux playbooks on     # expose authored playbooks to the swarm
glaux cache on         # semantic answer cache (skips repeat work)
```

## Useful next steps

```bash
glaux status           # model, safety, ledger size, capabilities
glaux skills           # what it has learned to do
glaux evolution        # how it has improved its own routing
glaux --help           # everything
```

## Where things live

State lives in `GLAUX_HOME` (default `~/.glaux`): the ledger, memory, skills,
workspace, playbooks, and logs. Delete it to start clean.

## Next

- [Configuration](configuration.md) — models, environment variables, capabilities
- [CLI reference](cli.md) — every command
- [Architecture](architecture.md) — how the swarm actually works
- [Security model](security.md) — the sandbox, the jail, and the trade-offs
