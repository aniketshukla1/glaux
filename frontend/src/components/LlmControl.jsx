import React, { useEffect, useState } from 'react'
import { getLlm, setLlm } from '../api.js'

export default function LlmControl({ onChange }) {
  const [llm, setLlmState] = useState(null)
  const [err, setErr] = useState(null)

  const load = async () => {
    try {
      setLlmState(await getLlm())
    } catch {
      setLlmState(null)
    }
  }
  useEffect(() => {
    load()
    // keep in sync if the backend LLM changes (e.g. via API)
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])

  if (!llm) return null

  const pick = async (backend, model) => {
    setErr(null)
    try {
      await setLlm(backend, model || null)
      await load()
      onChange && onChange()
    } catch (e) {
      setErr(`${backend} unavailable`)
      await load()
    }
  }

  const ollamaModels = llm.ollama?.models || []

  return (
    <div className="flex items-center gap-2 text-xs" title="LLM backend">
      <span className="text-slate-500">llm</span>
      <select
        value={llm.backend}
        onChange={(e) => {
          const b = e.target.value
          pick(b, b === 'ollama' ? ollamaModels[0] : undefined)
        }}
        className="glass px-2 py-1 bg-transparent text-slate-200 outline-none"
      >
        <option value="demo" className="bg-slate-800">demo</option>
        <option value="ollama" className="bg-slate-800" disabled={!llm.ollama?.reachable}>
          ollama{llm.ollama?.reachable ? '' : ' (offline)'}
        </option>
        <option value="anthropic" className="bg-slate-800" disabled={!llm.anthropic_key}>
          anthropic{llm.anthropic_key ? '' : ' (no key)'}
        </option>
      </select>
      {llm.backend === 'ollama' && ollamaModels.length > 0 && (
        <select
          value={llm.model || ollamaModels[0]}
          onChange={(e) => pick('ollama', e.target.value)}
          className="glass px-2 py-1 bg-transparent text-slate-200 outline-none"
        >
          {ollamaModels.map((m) => (
            <option key={m} value={m} className="bg-slate-800">
              {m}
            </option>
          ))}
        </select>
      )}
      <span className={llm.backend === 'demo' ? 'text-slate-500' : 'text-athena-accent'}>
        {llm.model_id}
      </span>
      {err && <span className="text-rose-300">{err}</span>}
    </div>
  )
}
