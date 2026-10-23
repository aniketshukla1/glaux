import React, { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, KeyRound, Boxes, Copy, ChevronDown, HardDrive, Square, Zap } from 'lucide-react'
import { getLlm, setLlm, setFastLlm, clearFastLlm, loadLocalModel, unloadLocalModel } from '../api.js'

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
  const [hfOpen, setHfOpen] = useState(false)
  const [hfRepo, setHfRepo] = useState('')
  const [hfRuntime, setHfRuntime] = useState('hf-router')
  const [copied, setCopied] = useState(false)
  const [lmOpen, setLmOpen] = useState(false)
  const [lmPath, setLmPath] = useState('')
  const [lmBusy, setLmBusy] = useState(false)
  const [lmErr, setLmErr] = useState(null)
  // model tiering: fast/cheap model for routing + reflection
  const [fastOpen, setFastOpen] = useState(false)
  const [fastBackend, setFastBackend] = useState('demo')
  const [fastModel, setFastModel] = useState('')
  const [fastKey, setFastKey] = useState('')
  const [fastBusy, setFastBusy] = useState(false)
  const [fastErr, setFastErr] = useState(null)

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

  const applyFast = async () => {
    setFastBusy(true)
    setFastErr(null)
    try {
      await setFastLlm(fastBackend, fastModel, fastKey, baseUrl)
      setFastKey('')
      await load()
      onChange && onChange()
    } catch (e) {
      try {
        const r = await fetch('/api/llm/fast', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ backend: fastBackend, model: fastModel || null, api_key: fastKey || null, base_url: baseUrl || null }),
        })
        const j = await r.json().catch(() => ({}))
        setFastErr(j.detail || e.message || 'Failed to set fast model')
      } catch {
        setFastErr(e.message || 'Failed to set fast model')
      }
    } finally {
      setFastBusy(false)
    }
  }

  const clearFast = async () => {
    setFastBusy(true)
    try {
      await clearFastLlm()
      await load()
      onChange && onChange()
    } finally {
      setFastBusy(false)
    }
  }

  const runtimes = llm?.hf_runtimes || []
  const runtime = runtimes.find((r) => r.id === hfRuntime) || runtimes[0]
  const repoFill = hfRepo.trim() || '{repo}'
  const hfCommand = runtime?.command ? runtime.command.replaceAll('{repo}', repoFill) : ''

  const useHfModel = () => {
    if (!runtime) return
    const repo = hfRepo.trim()
    setBackend(runtime.provider)
    setModel(runtime.model ? runtime.model.replaceAll('{repo}', repo) : repo)
    setBaseUrl(runtime.base_url || '')
    setApiKey('')
    setErr(null)
    setHfOpen(false)
  }

  const lm = llm?.local_model || { status: 'idle', running: false }

  const loadLocal = async () => {
    if (!lmPath.trim()) return
    setLmBusy(true)
    setLmErr(null)
    try {
      await loadLocalModel(lmPath.trim())
      await load()
      onChange && onChange()
    } catch {
      // surface the backend's detail (install hint / load error)
      try {
        const r = await fetch('/api/llm/local', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: lmPath.trim() }),
        })
        const j = await r.json().catch(() => ({}))
        setLmErr(j.detail || 'Failed to load the model.')
      } catch {
        setLmErr('Failed to load the model.')
      }
      await load()
    } finally {
      setLmBusy(false)
    }
  }

  const stopLocal = async () => {
    setLmBusy(true)
    try {
      await unloadLocalModel()
      await load()
      onChange && onChange()
    } finally {
      setLmBusy(false)
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
            <div className="flex items-center gap-1 text-xs mt-1" style={{ color: 'rgb(var(--ok))' }}>
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

      {err && <div className="text-xs" style={{ color: 'rgb(var(--bad))' }}>{err}</div>}

      {/* Model tiering: a fast/cheap model for routing + reflection */}
      <div className="card p-3 mt-1">
        <button onClick={() => setFastOpen((o) => !o)} className="flex items-center gap-2 text-muted text-sm w-full">
          <Zap className="w-3.5 h-3.5 text-accent" /> Fast model — routing &amp; reflection
          {llm.fast && <span className="text-xs text-accent ml-1 truncate">{llm.fast.model_id}</span>}
          <ChevronDown className={`w-3.5 h-3.5 ml-auto transition ${fastOpen ? 'rotate-180' : ''}`} />
        </button>
        {fastOpen && (
          <div className="mt-3 space-y-2.5">
            <p className="text-faint text-xs leading-relaxed">
              Route planning and reflection to a cheap, fast model (e.g. Haiku or Groq) while your
              primary model does the real work and writes the final answer — lower latency and cost.
            </p>
            <select value={fastBackend} onChange={(e) => setFastBackend(e.target.value)} className={inputCls}>
              <optgroup label="Built-in">
                <option value="demo">Demo (offline)</option>
                <option value="anthropic" disabled={!llm.anthropic_key}>Anthropic (Claude){llm.anthropic_key ? '' : ' — no key'}</option>
                <option value="ollama" disabled={!llm.ollama?.reachable}>Ollama (local){llm.ollama?.reachable ? '' : ' — offline'}</option>
              </optgroup>
              {grouped.map(([kind, list]) => (
                <optgroup key={kind} label={KIND_LABELS[kind]}>
                  {list.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}{p.requires_key ? (p.key_present ? ' ✓' : '') : ''}</option>
                  ))}
                </optgroup>
              ))}
            </select>
            {fastBackend !== 'demo' && (
              <input value={fastModel} onChange={(e) => setFastModel(e.target.value)} placeholder="model id (e.g. claude-haiku-4-5)" className={inputCls} />
            )}
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={applyFast} disabled={fastBusy} className="btn-accent px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-50">
                {fastBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Apply
              </button>
              {llm.fast && (
                <button onClick={clearFast} disabled={fastBusy} className="px-3 py-2 rounded-lg border border-line/20 text-muted text-sm hover:text-fg disabled:opacity-50">
                  Clear
                </button>
              )}
              <span className="text-faint text-xs truncate">
                {llm.fast ? <>tiering on: <span className="text-accent">{llm.fast.model_id}</span></> : 'off — one model for everything'}
              </span>
            </div>
            {fastErr && <div className="text-xs" style={{ color: 'rgb(var(--bad))' }}>{fastErr}</div>}
          </div>
        )}
      </div>

      {/* Run any model off the Hugging Face Hub */}
      {runtimes.length > 0 && (
        <div className="card p-3 mt-1">
          <button onClick={() => setHfOpen((o) => !o)} className="flex items-center gap-2 text-muted text-sm w-full">
            <Boxes className="w-3.5 h-3.5 text-accent" /> Run a Hugging Face model
            <ChevronDown className={`w-3.5 h-3.5 ml-auto transition ${hfOpen ? 'rotate-180' : ''}`} />
          </button>
          {hfOpen && (
            <div className="mt-3 space-y-2.5">
              <p className="text-faint text-xs leading-relaxed">
                Bring any model from the Hub — fine-tuned, quantized, your own. Athena drives the swarm;
                a runtime serves the model over the OpenAI API.
              </p>
              <input
                value={hfRepo}
                onChange={(e) => setHfRepo(e.target.value)}
                placeholder="HF repo id (e.g. Qwen/Qwen2.5-7B-Instruct)"
                className={inputCls}
              />
              <select value={hfRuntime} onChange={(e) => setHfRuntime(e.target.value)} className={inputCls}>
                {runtimes.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </select>
              {runtime?.note && <p className="text-faint text-xs">{runtime.note}</p>}
              {runtime?.local && hfCommand && (
                <div className="glass p-2.5 flex items-start gap-2">
                  <code className="text-xs text-muted break-all flex-1" style={{ fontFamily: 'ui-monospace, monospace' }}>
                    {hfCommand}
                  </code>
                  <button
                    onClick={() => { navigator.clipboard?.writeText(hfCommand); setCopied(true); setTimeout(() => setCopied(false), 1200) }}
                    className="btn p-1.5 shrink-0" aria-label="Copy command"
                  >
                    {copied ? <Check className="w-3.5 h-3.5" style={{ color: 'rgb(var(--ok))' }} /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
              )}
              <button
                onClick={useHfModel}
                disabled={!hfRepo.trim()}
                className="btn-accent px-3 py-2 text-sm disabled:opacity-50"
              >
                Use this model
              </button>
              <p className="text-faint text-xs">
                {runtime?.local
                  ? 'Run the command above, then click "Use this model" and Apply.'
                  : 'Sets the model — add your HF token above and Apply.'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Run a model straight from a local weights file */}
      <div className="card p-3">
        <button onClick={() => setLmOpen((o) => !o)} className="flex items-center gap-2 text-muted text-sm w-full">
          <HardDrive className="w-3.5 h-3.5 text-accent" /> Run a local model file
          {lm.running && <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'rgb(var(--ok))' }} />}
          <ChevronDown className={`w-3.5 h-3.5 ml-auto transition ${lmOpen ? 'rotate-180' : ''}`} />
        </button>
        {lmOpen && (
          <div className="mt-3 space-y-2.5">
            <p className="text-faint text-xs leading-relaxed">
              Point at a <code className="text-muted">.gguf</code> / <code className="text-muted">.safetensors</code> /
              <code className="text-muted"> .bin</code> / <code className="text-muted">.pt</code> file (or a model folder).
              Athena launches the right server and runs the swarm on it — ideal for testing your own or fine-tuned models.
            </p>
            <input
              value={lmPath}
              onChange={(e) => setLmPath(e.target.value)}
              placeholder="/path/to/model.gguf"
              className={inputCls}
            />
            <div className="flex items-center gap-2">
              <button onClick={loadLocal} disabled={lmBusy || !lmPath.trim()} className="btn-accent px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-50">
                {lmBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <HardDrive className="w-4 h-4" />}
                {lmBusy ? 'Loading…' : 'Load & run'}
              </button>
              {lm.running && (
                <button onClick={stopLocal} disabled={lmBusy} className="btn px-3 py-2 text-sm flex items-center gap-1.5 disabled:opacity-50">
                  <Square className="w-3.5 h-3.5" /> Stop
                </button>
              )}
            </div>
            {lm.running && (
              <div className="text-xs" style={{ color: 'rgb(var(--ok))' }}>
                running: {lm.runtime} · {lm.model} on :{lm.port}
              </div>
            )}
            {lmErr && <div className="text-xs whitespace-pre-wrap" style={{ color: 'rgb(var(--bad))' }}>{lmErr}</div>}
            <p className="text-faint text-xs">Loading large weights can take a while — Athena waits for the server to come up.</p>
          </div>
        )}
      </div>
    </div>
  )
}
