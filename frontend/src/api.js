// Thin client for the Athena backend (proxied to :8000 in dev via vite.config.js).

const json = (r) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}
const post = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(json)

// health / roster
export const getHealth = () => fetch('/api/health').then(json)
export const getAgents = () => fetch('/api/agents').then(json)

// swarm / ledger
export const getLedger = () => fetch('/api/ledger').then(json)
export const getBlock = (i) => fetch(`/api/block/${i}`).then(json)
export const resetLedger = () => fetch('/api/ledger', { method: 'DELETE' }).then(json)
export const dispatchTask = (directive, budget) =>
  post('/api/task', budget ? { directive, budget } : { directive })

// safety (kill switch)
export const getSafety = () => fetch('/api/safety').then(json)
export const setSafety = (mode) => post('/api/safety', { mode })

// memory
export const getMemory = (layer, q) =>
  fetch(`/api/memory/${layer}${q ? `?q=${encodeURIComponent(q)}` : ''}`).then(json)
export const addMemory = (layer, payload) => post(`/api/memory/${layer}`, payload)
