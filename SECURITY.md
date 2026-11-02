# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report it privately through
[GitHub Security Advisories](https://github.com/athena-swarm/athena/security/advisories/new).
Include a description, reproduction steps, and the impact you believe it has. You'll
get an acknowledgement within a few days, and credit in the fix unless you'd rather not.

## Supported versions

The latest released `1.x` line receives security fixes.

## What Glaux defends

Glaux runs model-generated code, so isolation is a core feature rather than an
afterthought. Findings in any of these are in scope and treated seriously:

- **Sandbox escape** — synthesized skills run in a WebAssembly guest with no ambient
  authority. Anything that lets guest code reach the host filesystem, network, or
  process table is a vulnerability.
- **Capability bypass** — the static capability check is meant to reject code that
  requests authority it wasn't granted.
- **Workspace jail escape** — the file workspace must confine reads and writes to its
  own directory, including via traversal, absolute paths, and symlinks.
- **Ledger forgery** — the hash chain and Ed25519 signatures must make undetected
  tampering or forged agent actions infeasible.
- **Capability-token forgery** — cross-agent handoff tokens must not be mintable or
  replayable by an unauthorised agent.
- **Authentication and session handling** on the HTTP API.

## Known, deliberate trade-offs

These are documented design decisions, not vulnerabilities:

- **The workspace is opt-in and grants real file access** inside its jail. Enabling it
  means agents can create and modify files there — that is its purpose.
- **MCP servers you connect run with the authority you give them.** Glaux cannot
  sandbox a third-party tool server.
- **The semantic answer cache is opt-in** and returns a prior answer for a
  near-identical request; it cannot account for conversation context. It is off by
  default for exactly this reason.
- **`dry-run` and `halted` safety modes are cooperative controls** for the swarm's own
  execution path, not a defence against hostile code that already escaped the sandbox.

## Handling secrets

Glaux never commits credentials. API keys live in your environment or the local
config under `GLAUX_HOME` (default `~/.glaux`), which is git-ignored. If you find a
path where a key is logged, echoed, or written into the ledger, please report it.
