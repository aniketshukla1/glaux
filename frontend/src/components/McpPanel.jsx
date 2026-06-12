import React, { useEffect, useState } from 'react'
import { callMcpTool, getMcpTools } from '../api.js'

export default function McpPanel() {
  const [tools, setTools] = useState([])
  const [selected, setSelected] = useState('')
  const [argsText, setArgsText] = useState('{}')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getMcpTools()
      .then((d) => {
        setTools(d.tools)
        if (d.tools[0]) setSelected(d.tools[0].name)
      })
      .catch(() => setTools([]))
  }, [])

  const onCall = async (e) => {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      let args = {}
      try {
        args = argsText.trim() ? JSON.parse(argsText) : {}
      } catch {
        setResult({ ok: false, error: 'args must be valid JSON' })
        return
      }
      setResult(await callMcpTool(selected, args))
    } finally {
      setBusy(false)
    }
  }

  const tool = tools.find((t) => t.name === selected)

  return (
    <section>
      <h2 className="text-slate-300 mb-3 flex items-center gap-2">
        🔌 MCP Tools <span className="text-xs text-slate-500">({tools.length})</span>
      </h2>

      <form onSubmit={onCall} className="glass p-3 mb-3 space-y-2">
        <div className="flex gap-2 items-center">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="glass px-2 py-2 bg-transparent text-sm text-slate-200 outline-none"
          >
            {tools.map((t) => (
              <option key={t.name} value={t.name} className="bg-slate-800">
                {t.name}
              </option>
            ))}
          </select>
          <input
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            placeholder='{"expression": "2 * (3 + 4)"}'
            className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-slate-200 placeholder-slate-500"
          />
          <button
            disabled={busy}
            className="px-3 py-2 rounded-lg border border-athena-accent/40 text-athena-accent text-sm hover:bg-athena-accent/10 disabled:opacity-50"
          >
            Call
          </button>
        </div>
        {tool && (
          <div className="text-xs text-slate-500">
            {tool.description} · schema {JSON.stringify(tool.input_schema)}
          </div>
        )}
      </form>

      {result && (
        <div
          className={`glass p-3 mb-3 text-sm border ${
            result.ok ? 'border-emerald-500/40' : 'border-rose-500/40'
          }`}
        >
          {result.ok ? (
            <span className="text-emerald-300">→ {JSON.stringify(result.result)}</span>
          ) : (
            <span className="text-rose-300">✗ {result.error}</span>
          )}
        </div>
      )}

      <div className="space-y-2">
        {tools.map((t) => (
          <div key={t.name} className="glass p-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-athena-accent2">{t.name}</span>
              <span className="text-xs text-slate-500">@ {t.server}</span>
            </div>
            <div className="text-xs text-slate-400 mt-1">{t.description}</div>
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-500 mt-3 leading-relaxed">
        Agents can call these tools (action <code>call_mcp</code>); every invocation is signed onto
        the ledger as an <code>MCP_TOOL</code> action. Real stdio/HTTP MCP servers plug in behind the
        same interface.
      </p>
    </section>
  )
}
