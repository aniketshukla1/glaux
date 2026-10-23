import React, { useEffect, useState } from 'react'
import { Cpu, ChevronDown, Loader2, Plug, SlidersHorizontal } from 'lucide-react'
import { getLlm, setLlm } from '../api.js'
import { Menu, MenuItem, MenuLabel, MenuSeparator } from './ui/Menu.jsx'

// Quick model switch in the composer: the offline demo, any pulled Ollama
// models, and Claude when a key is set. The full provider catalog lives in
// Settings → Model. In demo mode the chip says so and offers the way out.
export default function ModelSwitcher({ current, live, onChanged, onOpenModel }) {
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState(false)
  useEffect(() => { if (open) getLlm().then(setInfo).catch(() => setInfo({})) }, [open])

  const demo = !live
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
  const isActive = (o) => !!current && (o.id === 'claude' ? current.startsWith('claude') : current === o.id)

  const pick = async (o) => {
    setBusy(o.key)
    try { await setLlm(o.backend, o.model); await onChanged?.() } catch { /* surfaced in Settings */ } finally { setBusy('') }
  }

  return (
    <Menu side="top" align="start" width="w-64" onOpenChange={setOpen}
      trigger={(t) => (
        <button {...t} type="button" title={demo ? 'Demo mode — connect a model for real answers' : 'Switch model'}
          className={`flex items-center gap-1.5 h-7 px-2 rounded-md text-[12px] transition-colors ${
            demo ? 'text-accent bg-accent/[0.08] hover:bg-accent/[0.14]' : 'text-muted hover:text-fg hover:bg-line/[0.07]'
          }`}>
          {demo ? <Plug className="w-3.5 h-3.5" /> : <Cpu className="w-3.5 h-3.5" />}
          <span className="max-w-[160px] truncate">{demo ? 'Demo · connect a model' : (current || 'Model')}</span>
          <ChevronDown className="w-3 h-3 opacity-70 shrink-0" />
        </button>
      )}>
      <MenuLabel>Model</MenuLabel>
      {!info && <div className="px-2 py-1.5 text-faint text-[12px] flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</div>}
      {options.map((o) => (
        <MenuItem key={o.key} checked={busy === o.key ? undefined : isActive(o)} icon={busy === o.key ? Loader2 : undefined}
          onSelect={() => pick(o)}>{o.label}</MenuItem>
      ))}
      {info && options.length <= 1 && (
        <div className="px-2 py-1.5 text-[11.5px] text-faint leading-snug">No local models found. Connect a provider key or run Ollama.</div>
      )}
      <MenuSeparator />
      <MenuItem icon={demo ? Plug : SlidersHorizontal} onSelect={onOpenModel}>{demo ? 'Connect a model…' : 'All providers…'}</MenuItem>
    </Menu>
  )
}
