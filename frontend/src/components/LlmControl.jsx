import React, { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, KeyRound } from 'lucide-react'
import { getLlm, setLlm } from '../api.js'

const KIND_LABELS = {
  cloud: 'Frontier & major',
  aggregator: 'Aggregators',
  host: 'Fast inference / hosts',
  regional: 'Regional & international',
  local: 'Local / self-hosted',
  custom: 'Custom',
}
const KIND_ORDER = ['cloud', 'aggregator', 'host', 'regional', 'local', 'custom']

const ANTHROPIC_MODELS = ['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5']

export default function LlmControl({ onChange }) {
  const [llm, setLlmState] = useState(null)
  const [backend, setBackend] = useState('demo')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = async () => {
    try {
      const data = await getLlm()
      setLlmState(data)
      setBackend(data.backend)
      setModel(data.model || '')
    } catch {
      setLlmState(null)
    }
  }
  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])

  const providers = llm?.providers || []
  const byId = useMemo(() => Object.fromEntries(providers.map((p) => [p.id, p])), [providers])
  const current = byId[backend]

  // suggested models for the selected backend
  const suggestions = useMemo(() => {
    if (backend === 'ollama') return llm?.ollama?.models || []
    if (backend === 'anthropic') return ANTHROPIC_MODELS
    return current?.models || []
  }, [backend, current, llm])

  const onPickBackend = (b) => {
    setBackend(b)
    setErr(null)
    setApiKey('')
    setBaseUrl('')
    if (b === 'ollama') setModel((llm?.ollama?.models || [])[0] || '')
    else if (b === 'anthropic') setModel('claude-sonnet-4-6')
    else if (byId[b]) setModel(byId[b].default_model || '')
    else setModel('')
  }

  const apply = async () => {
    setBusy(true)
    setErr(null)
    try {
      await setLlm(backend, model, apiKey, baseUrl)
      setApiKey('')
      await load()
      onChange && onChange()
    } catch (e) {
      // surface the backend's detail message when available
      try {
        const r = await fetch('/api/llm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ backend, model: model || null, api_key: apiKey || null, base_url: baseUrl || null }),
        })
        const j = await r.json().catch(() => ({}))
        setErr(j.detail || e.message || 'Failed to switch model')
      } catch {
        setErr(e.message || 'Failed to switch model')
      }
    } finally {
      setBusy(false)
    }
  }

  if (!llm) return <div className="text-faint text-xs">Backend unreachable.</div>

  const grouped = KIND_ORDER.map((k) => [k, providers.filter((p) => p.kind === k)]).filter(([, l]) => l.length)
  const needsKey = current?.requires_key && !current?.key_present
  const isCustom = backend === 'custom'
  const inputCls = 'w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint'

  return (
    <div className="space-y-2.5">
      {/* provider */}
      <select value={backend} onChange={(e) => onPickBackend(e.target.value)} className={inputCls}>
        <optgroup label="Built-in">
          <option value="demo">Demo (offline)</option>
          <option value="anthropic" disabled={!llm.anthropic_key}>
            Anthropic (Claude){llm.anthropic_key ? '' : ' — no key'}
          </option>
          <option value="ollama" disabled={!llm.ollama?.reachable}>
            Ollama (local){llm.ollama?.reachable ? '' : ' — offline'}
          </option>
        </optgroup>
        {grouped.map(([kind, list]) => (
          <optgroup key={kind} label={KIND_LABELS[kind]}>
            {list.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {p.requires_key ? (p.key_present ? ' ✓' : '') : ''}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

      {/* model (free text + suggestions) */}
      {backend !== 'demo' && (
        <>
          <input
            list="athena-model-suggestions"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={current?.default_model || 'model id'}
            className={inputCls}
          />
          <datalist id="athena-model-suggestions">
            {suggestions.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </>
      )}

      {/* base url for custom */}
      {isCustom && (
        <input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://host/v1  (Azure, vLLM, a proxy…)"
          className={inputCls}
        />
      )}

      {/* api key — when the provider needs one and it isn't in the environment */}
      {current?.requires_key && (
        <div>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={current.key_present ? `override ${current.key_env} (optional)` : `paste API key (${current.key_env})`}
            className={inputCls}
          />
          {current.key_present && !apiKey && (
            <div className="flex items-center gap-1 text-xs mt-1" style={{ color: 'rgb(52 211 153)' }}>
              <Check className="w-3 h-3" /> key detected in {current.key_env}
            </div>
          )}
          {needsKey && !apiKey && (
            <div className="flex items-center gap-1 text-faint text-xs mt-1">
              <KeyRound className="w-3 h-3" /> stored in memory only — set {current.key_env} to persist
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <button onClick={apply} disabled={busy} className="btn-accent px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          Apply
        </button>
        <span className="text-faint text-xs truncate">
          active: <span className={llm.backend === 'demo' ? 'text-muted' : 'text-accent'}>{llm.model_id}</span>
        </span>
      </div>

      {err && <div className="text-xs" style={{ color: 'rgb(251 113 133)' }}>{err}</div>}
    </div>
  )
}
