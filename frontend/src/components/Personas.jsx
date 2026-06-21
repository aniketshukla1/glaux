import React, { useState } from 'react'
import { Plus, Pencil, Trash2, Check, X, Loader2 } from 'lucide-react'

const SUGGESTED = ['🧠', '🏴‍☠️', '👩‍🏫', '🧑‍💻', '🔬', '✍️', '📊', '⚖️', '🎯', '🩺']

function Editor({ initial, onSave, onCancel }) {
  const [name, setName] = useState(initial?.name || '')
  const [emoji, setEmoji] = useState(initial?.emoji || '🧠')
  const [instructions, setInstructions] = useState(initial?.instructions || '')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!name.trim()) return
    setBusy(true)
    try { await onSave({ name: name.trim(), emoji, instructions }) } finally { setBusy(false) }
  }
  return (
    <div className="card p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <input value={emoji} onChange={(e) => setEmoji(e.target.value.slice(0, 4))}
          className="w-12 text-center text-lg glass rounded-lg py-1.5 bg-transparent outline-none" aria-label="Emoji" />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Persona name" autoFocus
          className="flex-1 glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint" />
      </div>
      <div className="flex flex-wrap gap-1">
        {SUGGESTED.map((e) => (
          <button key={e} onClick={() => setEmoji(e)} className={`w-7 h-7 rounded-md grid place-items-center hover:bg-line/10 ${emoji === e ? 'bg-line/15' : ''}`}>{e}</button>
        ))}
      </div>
      <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={4}
        placeholder="System prompt — how this assistant should behave. e.g. 'You are a concise senior engineer. Prefer code. Cite trade-offs.'"
        className="w-full glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint resize-none" />
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="btn px-3 py-1.5 text-sm">Cancel</button>
        <button onClick={save} disabled={busy || !name.trim()} className="btn-accent px-3 py-1.5 text-sm flex items-center gap-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Save
        </button>
      </div>
    </div>
  )
}

export default function Personas({ personas = [], onCreate, onUpdate, onDelete }) {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(null) // id

  return (
    <div className="space-y-2.5">
      <p className="text-faint text-xs">Reusable system prompts. Apply one to a chat from the header to give Athena a custom personality or expertise.</p>

      {personas.map((p) =>
        editing === p.id ? (
          <Editor key={p.id} initial={p}
            onSave={async (data) => { await onUpdate(p.id, data); setEditing(null) }}
            onCancel={() => setEditing(null)} />
        ) : (
          <div key={p.id} className="card p-3 flex items-start gap-3 group">
            <div className="w-8 h-8 rounded-lg bg-line/8 grid place-items-center text-lg shrink-0">{p.emoji || '🧠'}</div>
            <div className="min-w-0 flex-1">
              <div className="text-fg text-sm font-medium">{p.name}</div>
              {p.instructions && <div className="text-faint text-xs mt-0.5 line-clamp-2">{p.instructions}</div>}
            </div>
            <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition">
              <button onClick={() => setEditing(p.id)} className="btn p-1.5" aria-label="Edit"><Pencil className="w-3.5 h-3.5" /></button>
              <button onClick={() => onDelete(p.id)} className="btn p-1.5 text-rose-300 hover:text-rose-200" aria-label="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        ),
      )}

      {adding ? (
        <Editor onSave={async (data) => { await onCreate(data); setAdding(false) }} onCancel={() => setAdding(false)} />
      ) : (
        <button onClick={() => setAdding(true)} className="btn w-full py-2.5 text-sm flex items-center justify-center gap-2">
          <Plus className="w-4 h-4" /> New persona
        </button>
      )}
    </div>
  )
}
