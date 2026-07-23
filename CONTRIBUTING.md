# Contributing to Athena

Thanks for your interest — issues and pull requests are both welcome.

## Getting set up

```bash
git clone https://github.com/athena-swarm/athena && cd athena
./install.sh                       # venv, native ledger kernel, dashboard
venv/bin/python -m pytest -q       # should be all green
```

You need Python 3.10+, a Rust toolchain (the ledger kernel is a native crate), and
Node.js for the dashboard. [AthenaDB](https://github.com/athena-swarm/athenadb) is
optional — clone it as a sibling directory to enable the memory layers.

## Ground rules

- **Tests come with the change.** Athena's whole premise is that it can prove what it
  did; a change without a test undermines that. Run the full suite before opening a PR.
- **Never weaken a safety boundary casually.** The sandbox's zero-ambient-authority
  default, the workspace jail, the capability checks, and the ledger's append-only
  chain are load-bearing. If a change touches one, say so explicitly in the PR.
- **Every self-modification stays gated, signed, and reversible.** New evolution
  operators must clear an evidence gate, write to the ledger, and be undoable.
- **Keep the UI and CLI at parity.** A new capability should be reachable from both.

## Pull requests

1. Branch off `main`.
2. Keep the change focused — one concern per PR.
3. Match the surrounding style (the codebase favours short, explanatory comments that
   say *why*, not *what*).
4. Describe the behaviour change and how you verified it.

## Running things

```bash
venv/bin/python -m pytest -q                 # full suite
venv/bin/python -m pytest tests/test_x.py    # one file
npm --prefix frontend run build              # dashboard
venv/bin/athena up                           # run the server
```

## Docs and the website

The markdown in `docs/` is the source of truth (and stays readable on GitHub). The
website is a Next.js app in `site/` that renders those docs into styled pages — after
editing a `.md`, regenerate so the site matches:

```bash
pip install markdown
python scripts/build_site_docs.py    # docs/*.md -> site/app/docs/*/page.tsx
cd site && npm run build             # optional: verify the static export
```

CI regenerates + rebuilds on deploy too, so a missed run won't ship a stale site. See
[site/README.md](site/README.md) for local development and deployment.

## Reporting bugs

Open an issue with what you expected, what happened, and the smallest reproduction you
can manage. `athena status` output and the relevant slice of `~/.athena/athena.log`
help a lot. Please redact API keys.

## Security

Don't open a public issue for a vulnerability — see [SECURITY.md](SECURITY.md).
