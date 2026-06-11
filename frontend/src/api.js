// Thin client for the Athena backend (proxied to :8000 in dev via vite.config.js).

const json = (r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export const getHealth = () => fetch('/api/health').then(json)
export const getLedger = () => fetch('/api/ledger').then(json)
export const getBlock = (i) => fetch(`/api/block/${i}`).then(json)
export const resetLedger = () => fetch('/api/ledger', { method: 'DELETE' }).then(json)

export const dispatchTask = (directive) =>
  fetch('/api/task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directive }),
  }).then(json)
