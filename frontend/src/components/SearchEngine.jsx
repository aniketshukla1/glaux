import React, { useEffect, useState } from 'react'
import { Globe, Check, Loader2, KeyRound } from 'lucide-react'
import { getSearchEngine, setSearchEngine } from '../api.js'

const LABELS = { brave: 'Brave', tavily: 'Tavily', serper: 'Serper', duckduckgo: 'DuckDuckGo' }
const OPTIONS = ['', 'brave', 'tavily', 'serper', 'duckduckgo']

// Which engine the swarm's web_search uses. Built-in DuckDuckGo needs no key;
// adding a Brave/Tavily/Serper key upgrades quality. Config is instance-level
// (admin-managed); everyone else sees which engine is active.
export default function SearchEngine({ user }) {
  const [status, setStatus] = useState(null)
  const [provider, setProvider] = useState('')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const isAdmin = user?.is_admin

  const load = async () => { try { const s = await getSearchEngine(); setStatus(s); setProvider(s.pinned || '') } catch { /* ignore */ } }
  useEffect(() => { load() }, [])
  if (!status) return null

  const providers = status.providers || {}
  const keyed = status.keyed || {}
  const needsKey = provider && providers[provider]?.needs_key

  const save = async () => {
    setBusy(true); setSaved(false)
    try {
      const keys = needsKey && key.trim() ? { [provider]: key.trim() } : undefined
      const s = await setSearchEngine(provider, keys)
      setStatus(s); setProvider(s.pinned || ''); setKey(''); setSaved(true); setTimeout(() => setSaved(false), 1500)
    } finally { setBusy(false) }
  }

  return (
    <div className="card p-3 space-y-2.5 border-accent/20 bg-accent/[0.04]">
      <div className="flex items-center gap-2">
        <Globe className="w-4 h-4 text-accent" />
        <span className="text-fg text-sm font-medium">Web search</span>
        <span className="ml-auto text-xs text-faint">engine: <span className="text-accent2">{LABELS[status.active] || status.active}</span></span>
      </div>
      <p className="text-faint text-xs leading-relaxed">
        Browsing is built in. DuckDuckGo needs no key and is the fallback; add a key for a stronger engine —
        <span className="text-muted"> Brave</span> is recommended (independent index, best agent quality).
      </p>

      {isAdmin ? (
        <>
          <div className="flex flex-wrap gap-1.5">
            {OPTIONS.map((p) => (
              <button key={p || 'auto'} onClick={() => setProvider(p)}
                className={`px-2.5 py-1 rounded-lg text-xs border transition flex items-center gap-1.5 ${
                  provider === p ? 'border-accent/40 text-accent bg-accent/10' : 'border-line/15 text-muted hover:text-fg'
                }`}>
                {p ? LABELS[p] : 'Auto'}
                {p && keyed[p] && <Check className="w-3 h-3 text-emerald-400" />}
              </button>
            ))}
          </div>
          {needsKey && (
            <div className="flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5 text-faint shrink-0" />
              <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
                placeholder={keyed[provider] ? 'Saved — paste to replace' : `${LABELS[provider]} API key`}
                className="flex-1 glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint" />
            </div>
          )}
          {needsKey && providers[provider]?.hint && <p className="text-faint text-[11px] leading-relaxed">{providers[provider].hint}</p>}
          <div className="flex justify-end">
            <button onClick={save} disabled={busy} className="btn-accent px-3 py-1.5 text-sm flex items-center gap-1.5 disabled:opacity-50">
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : null}
              {saved ? 'Saved' : 'Save'}
            </button>
          </div>
        </>
      ) : (
        <p className="text-faint text-xs">The search engine is managed by an admin.</p>
      )}
    </div>
  )
}
