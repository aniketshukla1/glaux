# Glaux Swarm Console

Real-time dashboard for the Glaux swarm: dispatch directives, watch the signed
ledger build up block by block, and audit the chain.

- **Task Console** — dispatch a directive to the swarm.
- **Swarm Feed** — every signed action (PLAN, CALL_AGENT, GRANT, THINK, OBSERVATION, REFLECT) as a collapsible card; expand to see payload + Ed25519 signature.
- **Chain Auditor** — native (Rust) verification of the whole chain; flags the exact block if tampering is detected.

## Run it

**1. Backend** (from the repo root, in the venv):

```bash
# offline demo mode (no key needed) — or set ANTHROPIC_API_KEY for real Claude
PYTHONPATH=src uvicorn core.api:app --port 8000 --reload
```

**2. Frontend** (from `frontend/`):

```bash
npm install
npm run dev      # http://localhost:5173  (proxies /api -> :8000)
```

Open http://localhost:5173 and dispatch a directive. With no API key the backend
uses a built-in demo planner so the full signed trace + verification still work;
set `ANTHROPIC_API_KEY` (and optionally `GLAUX_MODEL`) for real agent reasoning.

## API auth (optional)

The API is open by default. To require HMAC-signed requests, set a shared secret
on both sides:

```bash
# backend
GLAUX_API_SECRET=your-secret PYTHONPATH=src uvicorn core.api:app --port 8000
# frontend (frontend/.env.local, gitignored)
echo 'VITE_GLAUX_API_SECRET=your-secret' > frontend/.env.local
```

When enabled, every `/api/*` request must carry `X-Glaux-Timestamp` +
`X-Glaux-Signature` (HMAC-SHA256 over `ts\nMETHOD\npath\nsha256(body)`);
`/api/health` and `/api/auth` stay public so a client can bootstrap. The
dashboard signs automatically via Web Crypto.

## Notes

- The backend keeps one continuous ledger across dispatches (stable agent
  identities), so the Chain Auditor shows a growing, verifiable history. Use
  **Reset** to start a fresh chain.
- Live token-streaming over WebSocket is a planned next iteration; today the feed
  renders the full signed trace as soon as a dispatch completes.
