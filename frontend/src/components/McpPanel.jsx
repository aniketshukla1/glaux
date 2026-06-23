import React, { useCallback, useEffect, useState } from 'react'
import {
  Plug, Plus, RefreshCw, Trash2, Wrench, Server, Loader2, ChevronDown, Play, Globe,
} from 'lucide-react'
import {
  getMcpTools, callMcpTool, getMcpServers, addMcpServer, removeMcpServer, reconnectMcpServer,
} from '../api.js'

const STATUS_COLOR = {
  connected: 'rgb(52 211 153)',
  error: 'rgb(251 113 133)',
}

function StatusDot({ status }) {
  return (
    <span
      className="w-2 h-2 rounded-full shrink-0"
      style={{ background: STATUS_COLOR[status] || 'rgb(var(--faint))' }}
      title={status}
    />
  )
}

function AddServerForm({ onAdded }) {
  const [transport, setTransport] = useState('stdio')
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [argsText, setArgsText] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Give the server a name.')
    setBusy(true)
    try {
      const body =
        transport === 'stdio'
          ? { name, transport, command, args: argsText.trim() ? argsText.trim().split(/\s+/) : [] }
          : { name, transport, url }
      const { server } = await addMcpServer(body)
      if (server?.status === 'error') setError(server.error || 'Failed to connect.')
      else {
        setName(''); setCommand(''); setArgsText(''); setUrl('')
      }
      onAdded()
    } catch (e) {
      setError(e.message || 'Request failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4 text-accent" />
        <span className="text-fg text-sm font-medium">Connect an MCP server</span>
      </div>

      <div className="flex gap-1">
        {['stdio', 'http'].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTransport(t)}
            className={`px-2.5 py-1 rounded-md text-xs border transition ${
              transport === t ? 'border-accent/40 text-accent bg-accent/10' : 'border-line/15 text-faint hover:text-muted'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="name (e.g. filesystem)"
        className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
      />

      {transport === 'stdio' ? (
        <>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="command (e.g. npx)"
            className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
          />
          <input
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            placeholder="args (e.g. -y @modelcontextprotocol/server-filesystem ~/Documents)"
            className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
          />
        </>
      ) : (
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://server.example.com/mcp"
          className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
        />
      )}

      {error && <div className="text-xs" style={{ color: 'rgb(251 113 133)' }}>{error}</div>}

      <button disabled={busy} className="btn-accent px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-50">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
        {busy ? 'Connecting…' : 'Connect'}
      </button>
    </form>
  )
}

function ServerRow({ server, onChanged }) {
  const [busy, setBusy] = useState(false)
  const act = async (fn) => {
    setBusy(true)
    try { await fn(server.name) } finally { setBusy(false); onChanged() }
  }
  return (
    <div className="card p-3">
      <div className="flex items-center gap-2">
        <StatusDot status={server.status} />
        <span className="text-fg text-sm font-medium">{server.name}</span>
        <span className="text-faint text-[11px] px-1.5 py-0.5 rounded border border-line/15">{server.transport}</span>
        <span className="text-faint text-xs">{server.tool_count} tools</span>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => act(reconnectMcpServer)} disabled={busy} className="btn p-1.5" aria-label="Reconnect" title="Reconnect">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={() => act(removeMcpServer)} disabled={busy} className="btn p-1.5" aria-label="Remove" title="Remove">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div className="text-faint text-xs mt-1 font-mono break-all">
        {server.transport === 'stdio' ? [server.command, ...(server.args || [])].join(' ') : server.url}
      </div>
      {server.status === 'error' && server.error && (
        <div className="text-xs mt-1" style={{ color: 'rgb(251 113 133)' }}>{server.error}</div>
      )}
    </div>
  )
}

function ToolTester({ tools }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState('')
  const [argsText, setArgsText] = useState('{}')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!selected && tools[0]) setSelected(tools[0].name)
  }, [tools, selected])

  const call = async (e) => {
    e.preventDefault()
    setBusy(true); setResult(null)
    try {
      let args = {}
      try { args = argsText.trim() ? JSON.parse(argsText) : {} } catch { setResult({ ok: false, error: 'args must be valid JSON' }); return }
      setResult(await callMcpTool(selected, args))
    } finally { setBusy(false) }
  }

  if (!tools.length) return null
  return (
    <div className="card p-3">
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 text-muted text-sm w-full">
        <Play className="w-3.5 h-3.5" /> Try a tool
        <ChevronDown className={`w-3.5 h-3.5 ml-auto transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <form onSubmit={call} className="mt-3 space-y-2">
          <div className="flex gap-2">
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="glass px-2 py-2 bg-transparent text-sm text-fg outline-none"
            >
              {tools.map((t) => (
                <option key={`${t.server}.${t.name}`} value={t.name} className="bg-panel text-fg">{t.name}</option>
              ))}
            </select>
            <input
              value={argsText}
              onChange={(e) => setArgsText(e.target.value)}
              placeholder='{"expression": "2 * (3 + 4)"}'
              className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
            />
            <button disabled={busy} className="btn-accent px-3 py-2 text-sm disabled:opacity-50">Call</button>
          </div>
          {result && (
            <div className="text-sm" style={{ color: result.ok ? 'rgb(52 211 153)' : 'rgb(251 113 133)' }}>
              {result.ok ? `→ ${JSON.stringify(result.result)}` : `✗ ${result.error}`}
            </div>
          )}
        </form>
      )}
    </div>
  )
}

export default function McpPanel() {
  const [tools, setTools] = useState([])
  const [servers, setServers] = useState([])

  const refresh = useCallback(async () => {
    try {
      const [t, s] = [await getMcpTools(), await getMcpServers()]
      setTools(t.tools || [])
      setServers(s.servers || [])
    } catch {
      setTools([]); setServers([])
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <Plug className="w-4 h-4 text-accent" />
        <h2 className="text-fg font-medium">Tools</h2>
        <span className="text-faint text-xs">{tools.length} available · {servers.length} servers</span>
      </div>

      {tools.some((t) => t.server === 'athena-web') && (
        <div className="card p-3 flex items-start gap-2.5 border-accent/20 bg-accent/[0.04]">
          <Globe className="w-4 h-4 text-accent mt-0.5 shrink-0" />
          <div className="text-xs text-muted leading-relaxed">
            <span className="text-fg font-medium">Web browsing is built in.</span> The swarm can
            <code className="text-accent2 mx-1">web_search</code> the live web and
            <code className="text-accent2 mx-1">web_fetch</code> any page to read it — no setup, every call signed to the ledger.
          </div>
        </div>
      )}

      <AddServerForm onAdded={refresh} />

      {servers.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-faint text-xs uppercase tracking-wide">
            <Server className="w-3.5 h-3.5" /> Connected servers
          </div>
          {servers.map((s) => <ServerRow key={s.name} server={s} onChanged={refresh} />)}
        </div>
      )}

      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-faint text-xs uppercase tracking-wide">
          <Wrench className="w-3.5 h-3.5" /> Tools the swarm can call
        </div>
        {tools.map((t) => (
          <div key={`${t.server}.${t.name}`} className="card p-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-accent2 font-medium">{t.name}</span>
              <span className="text-faint text-xs">@ {t.server}</span>
            </div>
            {t.description && <div className="text-muted text-xs mt-1">{t.description}</div>}
          </div>
        ))}
      </div>

      <ToolTester tools={tools} />

      <p className="text-faint text-xs leading-relaxed">
        Connect any MCP server (stdio or HTTP) — its tools join the swarm's toolbox. Every invocation
        is signed onto the ledger as an <code className="text-muted">MCP_TOOL</code> action. Server
        configs persist across restarts.
      </p>
    </section>
  )
}
