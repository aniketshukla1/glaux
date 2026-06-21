import React, { useEffect, useState } from 'react'
import { MessageSquare, X, Search, ExternalLink, Loader2, Check } from 'lucide-react'
import Modal from './Modal.jsx'
import { getMessaging, setMessaging } from '../api.js'
import { avatarColor } from '../lib/avatar.js'

const STATUS = {
  disabled: { label: 'Disabled', cls: 'text-faint', dot: 'rgb(var(--line))' },
  needs_setup: { label: 'Needs setup', cls: 'text-amber-300', dot: '#fbbf24' },
  ready: { label: 'Ready', cls: 'text-emerald-300', dot: '#34d399' },
}

function PlatformIcon({ p, size = 28 }) {
  return (
    <div className="rounded-lg grid place-items-center text-white font-semibold shrink-0"
      style={{ width: size, height: size, background: avatarColor(p.id), fontSize: size * 0.45 }}>
      {p.label[0]}
    </div>
  )
}

function FieldGroup({ title, fields, gw, edits, setEdit }) {
  if (!fields.length) return null
  return (
    <div className="mt-6">
      <div className="text-faint text-[11px] uppercase tracking-wide mb-3">{title}</div>
      <div className="space-y-4">
        {fields.map((f) => {
          const secretSet = f.secret && gw?.configured_secrets?.includes(f.key)
          const val = f.key in edits ? edits[f.key] : (gw?.config?.[f.key] ?? '')
          return (
            <div key={f.key} className="flex items-start gap-4">
              <div className="w-1/2 min-w-0">
                <div className="text-fg text-sm font-medium">{f.label}</div>
                {f.hint && <p className="text-faint text-xs mt-0.5">{f.hint}</p>}
              </div>
              <input
                type={f.secret ? 'password' : 'text'}
                value={f.secret ? (edits[f.key] ?? '') : val}
                onChange={(e) => setEdit(f.key, e.target.value)}
                placeholder={secretSet ? 'Saved — paste to replace' : f.placeholder}
                className="flex-1 glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint"
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Messaging({ open, onClose }) {
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(null)
  const [query, setQuery] = useState('')
  const [edits, setEdits] = useState({})
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!open) return
    (async () => {
      const d = await getMessaging()
      setData(d)
      const first = d.platforms[0]?.id
      setSel((s) => s || first)
      setEnabled(d.gateways[sel || first]?.enabled || false)
    })()
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null
  const platform = data?.platforms.find((p) => p.id === sel)
  const gw = data?.gateways[sel]
  const list = (data?.platforms || []).filter((p) => p.label.toLowerCase().includes(query.trim().toLowerCase()))

  const pick = (id) => { setSel(id); setEdits({}); setSaved(false); setEnabled(data.gateways[id]?.enabled || false) }
  const setEdit = (k, v) => { setEdits((e) => ({ ...e, [k]: v })); setSaved(false) }
  const save = async () => {
    setBusy(true)
    try {
      const { gateway } = await setMessaging(sel, edits, enabled)
      setData((prev) => ({ ...prev, gateways: { ...prev.gateways, [sel]: gateway } }))
      setEdits({}); setSaved(true); setTimeout(() => setSaved(false), 1500)
    } finally { setBusy(false) }
  }

  const required = (platform?.fields || []).filter((f) => f.required)
  const recommended = (platform?.fields || []).filter((f) => f.recommended && !f.required)
  const optional = (platform?.fields || []).filter((f) => !f.required && !f.recommended)
  const st = STATUS[gw?.status] || STATUS.disabled

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-line/10 shrink-0">
        <MessageSquare className="w-4 h-4 text-muted" />
        <h2 className="text-fg font-medium">Messaging</h2>
        <button onClick={onClose} className="btn p-1.5 ml-auto" aria-label="Close"><X className="w-4 h-4" /></button>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* platform list */}
        <div className="w-60 shrink-0 border-r border-line/10 flex flex-col">
          <div className="p-2.5">
            <div className="glass flex items-center gap-2 px-2.5 rounded-lg">
              <Search className="w-3.5 h-3.5 text-faint shrink-0" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search messaging…"
                className="flex-1 min-w-0 bg-transparent outline-none text-sm text-fg placeholder-faint py-1.5" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
            {!data && <div className="p-3 text-faint text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>}
            {list.map((p) => {
              const s = STATUS[data.gateways[p.id]?.status] || STATUS.disabled
              return (
                <button key={p.id} onClick={() => pick(p.id)}
                  className={`w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm transition ${sel === p.id ? 'bg-line/10 text-fg' : 'text-muted hover:text-fg hover:bg-line/5'}`}>
                  <PlatformIcon p={p} />
                  <span className="truncate flex-1 text-left">{p.label}</span>
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: s.dot }} />
                </button>
              )
            })}
          </div>
        </div>

        {/* config panel */}
        <div className="flex-1 overflow-y-auto">
          {platform && (
            <div className="max-w-2xl mx-auto px-7 py-6">
              <div className="flex items-center gap-3">
                <PlatformIcon p={platform} size={36} />
                <div className="min-w-0">
                  <h3 className="text-fg font-medium">{platform.label}</h3>
                  <p className="text-faint text-sm">{platform.blurb}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 mt-3">
                <span className={`text-xs px-2 py-1 rounded-md border border-line/15 flex items-center gap-1.5 ${st.cls}`}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: st.dot }} /> {st.label}
                </span>
                <span className="text-xs px-2 py-1 rounded-md border border-line/15 text-faint">Runtime wired next</span>
              </div>
              {platform.guide && (
                <a href={platform.guide} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-accent text-sm mt-3 underline underline-offset-2">
                  Open setup guide <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}

              <FieldGroup title="Required" fields={required} gw={gw} edits={edits} setEdit={setEdit} />
              <FieldGroup title="Recommended" fields={recommended} gw={gw} edits={edits} setEdit={setEdit} />
              <FieldGroup title="Optional" fields={optional} gw={gw} edits={edits} setEdit={setEdit} />

              <div className="flex items-center gap-3 mt-7 pt-5 border-t border-line/10">
                <button onClick={() => setEnabled((v) => !v)} role="switch" aria-checked={enabled}
                  className={`relative w-10 h-6 rounded-full transition ${enabled ? 'bg-accent' : 'bg-line/25'}`}>
                  <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${enabled ? 'left-[18px]' : 'left-0.5'}`} />
                </button>
                <span className="text-sm text-muted">{enabled ? 'Enabled' : 'Disabled'}</span>
                <button onClick={save} disabled={busy} className="btn-accent px-3.5 py-2 text-sm ml-auto flex items-center gap-1.5 disabled:opacity-50">
                  {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : null}
                  {saved ? 'Saved' : 'Save changes'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
