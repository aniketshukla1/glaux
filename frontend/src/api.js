// Thin client for the Athena backend (proxied to :8000 in dev via vite.config.js).
//
// When VITE_ATHENA_API_SECRET is set, every request is HMAC-signed (Web Crypto)
// to match the backend's env-gated auth. Otherwise requests are sent plain.

const SECRET = import.meta.env.VITE_ATHENA_API_SECRET || ''
const enc = new TextEncoder()

// --- session token (account auth) ---------------------------------------
const TOKEN_KEY = 'athena-token'
export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}
export const clearToken = () => setToken('')

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
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const opts = { method, headers }
  if (hasBody) {
    opts.headers = { 'Content-Type': 'application/json', ...headers }
    opts.body = bodyStr
  }
  const r = await fetch(url, opts)
  if (!r.ok) {
    // A 401 means our token is missing/expired — drop it and tell the app to
    // bounce to the sign-in screen (but not for the auth endpoints themselves,
    // where 401 is an expected "wrong password" result).
    if (r.status === 401 && !path.startsWith('/api/auth')) {
      clearToken()
      try { window.dispatchEvent(new CustomEvent('athena-unauthorized')) } catch { /* non-browser */ }
    }
    // Prefer the server's explanation (FastAPI `detail`) over a bare status code.
    let detail = `HTTP ${r.status}`
    try {
      const j = await r.json()
      if (j && j.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* response body wasn't JSON */
    }
    throw new Error(detail)
  }
  return r.json()
}

// health / roster / auth
export const getHealth = () => request('GET', '/api/health')
export const getAgents = () => request('GET', '/api/agents')
export const getAuth = () => request('GET', '/api/auth')

// accounts (signup / login / profile)
export const getAuthState = () => request('GET', '/api/auth/state')
export const signup = (email, password, name) =>
  request('POST', '/api/auth/signup', { email, password, name: name || '' })
export const login = (email, password) => request('POST', '/api/auth/login', { email, password })
export const getMe = () => request('GET', '/api/auth/me')
export const updateProfile = (patch) => request('PATCH', '/api/auth/me', patch)
export const changePassword = (current, next) =>
  request('POST', '/api/auth/password', { current, new: next })
export const logoutEverywhere = () => request('POST', '/api/auth/logout', {})
export const deleteAccount = () => request('DELETE', '/api/auth/me')

// email verification + password reset
export const verifyEmail = (token) => request('POST', '/api/auth/verify', { token })
export const resendVerification = () => request('POST', '/api/auth/resend-verification', {})
export const forgotPassword = (email) => request('POST', '/api/auth/forgot', { email })
export const resetPassword = (token, password) => request('POST', '/api/auth/reset', { token, password })

// social login
export const oauthStart = (provider) => request('GET', `/api/auth/oauth/${provider}/start`)
export const signupWithInvite = (email, password, name, invite) =>
  request('POST', '/api/auth/signup', { email, password, name: name || '', invite: invite || null })

// team / admin
export const getAdminUsers = () => request('GET', '/api/admin/users')
export const updateAdminUser = (id, patch) => request('PATCH', `/api/admin/users/${encodeURIComponent(id)}`, patch)
export const deleteAdminUser = (id) => request('DELETE', `/api/admin/users/${encodeURIComponent(id)}`)
export const createInvite = () => request('POST', '/api/admin/invites', {})

// swarm / ledger
export const getLedger = () => request('GET', '/api/ledger')
export const getBlock = (i) => request('GET', `/api/block/${i}`)
export const resetLedger = () => request('DELETE', '/api/ledger')
export const dispatchTask = (directive, budget) =>
  request('POST', '/api/task', budget ? { directive, budget } : { directive })
export const stopTask = () => request('POST', '/api/task/stop', {})

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
export const setLlm = (backend, model, apiKey, baseUrl) =>
  request('POST', '/api/llm', {
    backend,
    model: model || null,
    api_key: apiKey || null,
    base_url: baseUrl || null,
  })
// local model files (.gguf / .safetensors / .bin / .pt)
export const planLocalModel = (path) => request('POST', '/api/llm/local/plan', { path })
export const loadLocalModel = (path) => request('POST', '/api/llm/local', { path })
export const unloadLocalModel = () => request('DELETE', '/api/llm/local')

// workspace: projects + sessions
export const getWorkspace = () => request('GET', '/api/workspace')
export const getSession = (id) => request('GET', `/api/sessions/${encodeURIComponent(id)}`)
export const createSession = (title, projectId) =>
  request('POST', '/api/sessions', { title: title || null, project_id: projectId || null })
export const activateSession = (id) => request('POST', `/api/sessions/${encodeURIComponent(id)}/activate`)
export const updateSession = (id, patch) => request('PATCH', `/api/sessions/${encodeURIComponent(id)}`, patch)
export const deleteSession = (id) => request('DELETE', `/api/sessions/${encodeURIComponent(id)}`)
export const pinSession = (id, pinned) => request('POST', `/api/sessions/${encodeURIComponent(id)}/pin`, { pinned })
export const searchConversations = (q) => request('GET', `/api/search?q=${encodeURIComponent(q)}`)
export const createPersona = (name, instructions, emoji) =>
  request('POST', '/api/personas', { name, instructions: instructions || null, emoji: emoji || null })
export const updatePersona = (id, patch) => request('PATCH', `/api/personas/${encodeURIComponent(id)}`, patch)
export const deletePersona = (id) => request('DELETE', `/api/personas/${encodeURIComponent(id)}`)
export const createProject = (name, instructions) =>
  request('POST', '/api/projects', { name, instructions: instructions || null })
export const updateProject = (id, patch) => request('PATCH', `/api/projects/${encodeURIComponent(id)}`, patch)
export const deleteProject = (id) => request('DELETE', `/api/projects/${encodeURIComponent(id)}`)

// messaging gateways
export const getMessaging = () => request('GET', '/api/messaging')
export const setMessaging = (platform, config, enabled) =>
  request('POST', `/api/messaging/${encodeURIComponent(platform)}`, { config: config || {}, enabled: !!enabled })

// scheduled jobs (cron)
export const getSchedules = () => request('GET', '/api/schedules')
export const addSchedule = (directive, schedule) => request('POST', '/api/schedules', { directive, schedule })
export const removeSchedule = (id) => request('DELETE', `/api/schedules/${encodeURIComponent(id)}`)
export const enableSchedule = (id, enabled) =>
  request('POST', `/api/schedules/${encodeURIComponent(id)}/enable`, { enabled })
export const runSchedule = (id) => request('POST', `/api/schedules/${encodeURIComponent(id)}/run`)
