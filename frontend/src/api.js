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

// skills (synthesis + curation)
export const getSkills = () => fetch('/api/skills').then(json)
export const synthesizeSkill = (task) => post('/api/skills/synthesize', { task })
export const useSkill = (id, success) => post(`/api/skills/${id}/use`, { success })
export const approveSkill = (id) => post(`/api/skills/${id}/approve`, {})
export const rejectSkill = (id) => post(`/api/skills/${id}/reject`, {})

// approval mode (HITL gate)
export const getApproval = () => fetch('/api/approval').then(json)
export const setApproval = (mode) => post('/api/approval', { mode })

// eval harness
export const runEval = () => post('/api/eval/run', {})
export const getEvalRuns = () => fetch('/api/eval/runs').then(json)

// observability
export const getMetrics = () => fetch('/api/metrics').then(json)

// MCP tools
export const getMcpTools = () => fetch('/api/mcp/tools').then(json)
export const callMcpTool = (tool, args) => post('/api/mcp/call', { tool, args })

// LLM backend
export const getLlm = () => fetch('/api/llm').then(json)
export const setLlm = (backend, model) => post('/api/llm', { backend, model })
