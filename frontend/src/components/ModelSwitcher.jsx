import React, { useEffect, useRef, useState } from 'react'
import { Cpu, ChevronDown, Check, Loader2, SlidersHorizontal } from 'lucide-react'
import { getLlm, setLlm } from '../api.js'

// Compact model picker for the top bar — quick switches between the readily
// available backends (demo, any pulled Ollama models, Anthropic if keyed); the
// full 30-provider catalog lives in Settings → Model.
export default function ModelSwitcher({ current, live, onChanged, onOpenModel }) {
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    getLlm().then(setInfo).catch(() => {})
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const options = []
  if (info) {
    options.push({ key: 'demo', backend: 'demo', model: null, label: 'Demo (offline)', id: 'demo-offline' })
    if (info.ollama?.reachable) {
      for (const m of info.ollama.models || []) {
        if (/embed/i.test(m)) continue  // embedding models aren't chat models
        options.push({ key: `ollama:${m}`, backend: 'ollama', model: m, label: m, id: `ollama:${m}` })
      }
    }
    if (info.anthropic_key) options.push({ key: 'anthropic', backend: 'anthropic', model: null, label: 'Claude (Anthropic)', id: 'claude' })
  }
  const isActive = (o) => current && (o.id === 'claude' ? current.startsWith('claude') : current === o.id)

  const pick = async (o) => {
    setBusy(o.key)
    try { await setLlm(o.backend, o.model); await onChanged?.(); setOpen(false) }
    catch { /* surfaced elsewhere */ } finally { setBusy('') }
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} title="Switch model"
        className="hidden md:flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-line/15 text-muted hover:text-fg hover:border-line/30 transition">
        <Cpu className="w-3.5 h-3.5" style={{ color: live ? 'rgb(var(--accent))' : undefined }} />
        <span className="max-w-[150px] truncate">{current || '—'}</span>
        <ChevronDown className="w-3 h-3 shrink-0" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1.5 w-64 card p-1.5 shadow-xl z-50 animate-fade-in">
          {!info && <div className="px-2 py-2 text-faint text-xs flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</div>}
          {options.map((o) => (
            <button key={o.key} onClick={() => pick(o)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-muted hover:text-fg hover:bg-line/8 transition">
              {busy === o.key ? <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                : isActive(o) ? <Check className="w-3.5 h-3.5 text-accent shrink-0" /> : <span className="w-3.5 shrink-0" />}
              <span className="truncate">{o.label}</span>
            </button>
          ))}
          <div className="border-t border-line/10 mt-1 pt-1">
            <button onClick={() => { setOpen(false); onOpenModel?.() }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-muted hover:text-fg hover:bg-line/8 transition">
              <SlidersHorizontal className="w-3.5 h-3.5 shrink-0" /> More providers in Settings…
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
