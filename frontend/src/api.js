// Thin client for the Athena backend (proxied to :8000 in dev via vite.config.js).
//
// When VITE_ATHENA_API_SECRET is set, every request is HMAC-signed (Web Crypto)
// to match the backend's env-gated auth. Otherwise requests are sent plain.

const SECRET = import.meta.env.VITE_ATHENA_API_SECRET || ''
const enc = new TextEncoder()

const hex = (buf) =>
  [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')

const sha256hex = async (s) => hex(await crypto.subtle.digest('SHA-256', enc.encode(s)))

async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  return hex(await crypto.subtle.sign('HMAC', key, enc.encode(msg)))
}

async function authHeaders(method, path, bodyStr) {
  if (!SECRET) return {}
  const ts = Math.floor(Date.now() / 1000).toString()
  const canonical = `${ts}\n${method.toUpperCase()}\n${path}\n${await sha256hex(bodyStr || '')}`
  return { 'X-Athena-Timestamp': ts, 'X-Athena-Signature': await hmacHex(SECRET, canonical) }
}

async function request(method, url, bodyObj) {
  const path = url.split('?')[0]
  const hasBody = bodyObj !== undefined
  const bodyStr = hasBody ? JSON.stringify(bodyObj) : ''
  const headers = await authHeaders(method, path, bodyStr)
  const opts = { method, headers }
  if (hasBody) {
    opts.headers = { 'Content-Type': 'application/json', ...headers }
    opts.body = bodyStr
  }
  const r = await fetch(url, opts)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// health / roster / auth
export const getHealth = () => request('GET', '/api/health')
export const getAgents = () => request('GET', '/api/agents')
export const getAuth = () => request('GET', '/api/auth')

// swarm / ledger
export const getLedger = () => request('GET', '/api/ledger')
export const getBlock = (i) => request('GET', `/api/block/${i}`)
export const resetLedger = () => request('DELETE', '/api/ledger')
export const dispatchTask = (directive, budget) =>
  request('POST', '/api/task', budget ? { directive, budget } : { directive })

// safety (kill switch)
export const getSafety = () => request('GET', '/api/safety')
export const setSafety = (mode) => request('POST', '/api/safety', { mode })

// approval mode (HITL gate)
export const getApproval = () => request('GET', '/api/approval')
export const setApproval = (mode) => request('POST', '/api/approval', { mode })

// memory
export const getMemory = (layer, q) =>
  request('GET', `/api/memory/${layer}${q ? `?q=${encodeURIComponent(q)}` : ''}`)
export const addMemory = (layer, payload) => request('POST', `/api/memory/${layer}`, payload)

// skills (synthesis + curation)
export const getSkills = () => request('GET', '/api/skills')
export const synthesizeSkill = (task) => request('POST', '/api/skills/synthesize', { task })
export const useSkill = (id, success) => request('POST', `/api/skills/${id}/use`, { success })
export const approveSkill = (id) => request('POST', `/api/skills/${id}/approve`, {})
export const rejectSkill = (id) => request('POST', `/api/skills/${id}/reject`, {})

// eval harness
export const runEval = () => request('POST', '/api/eval/run', {})
export const getEvalRuns = () => request('GET', '/api/eval/runs')

// observability
export const getMetrics = () => request('GET', '/api/metrics')

// MCP tools + servers
export const getMcpTools = () => request('GET', '/api/mcp/tools')
export const callMcpTool = (tool, args) => request('POST', '/api/mcp/call', { tool, args })
export const getMcpServers = () => request('GET', '/api/mcp/servers')
export const addMcpServer = (server) => request('POST', '/api/mcp/servers', server)
export const removeMcpServer = (name) => request('DELETE', `/api/mcp/servers/${encodeURIComponent(name)}`)
export const reconnectMcpServer = (name) =>
  request('POST', `/api/mcp/servers/${encodeURIComponent(name)}/reconnect`)

// LLM backend
export const getLlm = () => request('GET', '/api/llm')
export const setLlm = (backend, model) => request('POST', '/api/llm', { backend, model })
