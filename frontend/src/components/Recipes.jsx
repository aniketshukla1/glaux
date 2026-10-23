import React, { useState } from 'react'
import { Plus, Pencil, Trash2, Check, Loader2, Sparkles } from 'lucide-react'

const SUGGESTED = ['📋', '🔬', '🧑‍💻', '🔍', '📊', '✍️', '⚖️', '🧭', '🐛', '📰']

// One-click starters the user can drop in and tweak. {{placeholders}} are
// selected first when the recipe is run from the composer.
const STARTERS = [
  { emoji: '🔬', name: 'Deep research', description: 'Multi-source web research with citations',
    prompt: 'Research {{topic}} in depth. Use web_search and web_fetch to gather current, credible sources, then give a structured summary with key findings, trade-offs, and a list of cited sources.' },
  { emoji: '⚖️', name: 'Compare & recommend', description: 'Weigh options on real criteria',
    prompt: 'Compare {{option A}} vs {{option B}} for {{use case}}. Evaluate on performance, cost, ecosystem, and operational complexity. End with a clear recommendation and why.' },
  { emoji: '🐛', name: 'Debug an issue', description: 'Reproduce, isolate, fix',
    prompt: 'Debug this problem: {{describe the bug, including the error and what you expected}}. Form hypotheses, identify the most likely root cause, and propose a concrete fix.' },
  { emoji: '🧑‍💻', name: 'Build a feature', description: 'Spec → implementation plan → code',
    prompt: 'Implement {{feature}} in {{language/framework}}. Outline the approach, then write clean, working code with brief notes on edge cases and how to test it.' },
  { emoji: '📰', name: 'Summarize & extract', description: 'TL;DR + action items',
    prompt: 'Summarize the following and pull out the key decisions and action items:\n\n{{paste text or a URL}}' },
]

function Editor({ initial, onSave, onCancel }) {
  const [name, setName] = useState(initial?.name || '')
  const [emoji, setEmoji] = useState(initial?.emoji || '📋')
  const [description, setDescription] = useState(initial?.description || '')
  const [prompt, setPrompt] = useState(initial?.prompt || '')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!name.trim()) return
    setBusy(true)
    try { await onSave({ name: name.trim(), emoji, description, prompt }) } finally { setBusy(false) }
  }
  return (
    <div className="card p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <input value={emoji} onChange={(e) => setEmoji(e.target.value.slice(0, 4))}
          className="w-12 text-center text-lg glass rounded-lg py-1.5 bg-transparent outline-none" aria-label="Emoji" />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Recipe name" autoFocus
          className="flex-1 glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint" />
      </div>
      <div className="flex flex-wrap gap-1">
        {SUGGESTED.map((e) => (
          <button key={e} onClick={() => setEmoji(e)} className={`w-7 h-7 rounded-md grid place-items-center hover:bg-line/10 ${emoji === e ? 'bg-line/15' : ''}`}>{e}</button>
        ))}
      </div>
      <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short description (optional)"
        className="w-full glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint" />
      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5}
        placeholder="The task prompt. Use {{placeholders}} for the bits you fill in each time — they're selected first when you run the recipe."
        className="w-full glass px-3 py-2 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint resize-none font-mono leading-relaxed" />
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="btn px-3 py-1.5 text-sm">Cancel</button>
        <button onClick={save} disabled={busy || !name.trim()} className="btn-accent px-3 py-1.5 text-sm flex items-center gap-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Save
        </button>
      </div>
    </div>
  )
}

export default function Recipes({ recipes = [], onCreate, onUpdate, onDelete }) {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(null)

  return (
    <div className="space-y-2.5">
      <p className="text-faint text-xs">Saved task templates. Type <code className="text-muted">/</code> in the composer to run one — placeholders like <code className="text-muted">{'{{topic}}'}</code> get selected so you can fill them fast.</p>

      {recipes.map((r) =>
        editing === r.id ? (
          <Editor key={r.id} initial={r}
            onSave={async (data) => { await onUpdate(r.id, data); setEditing(null) }}
            onCancel={() => setEditing(null)} />
        ) : (
          <div key={r.id} className="card p-3 flex items-start gap-3 group">
            <div className="w-8 h-8 rounded-lg bg-line/8 grid place-items-center text-lg shrink-0">{r.emoji || '📋'}</div>
            <div className="min-w-0 flex-1">
              <div className="text-fg text-sm font-medium">{r.name}</div>
              {r.description && <div className="text-muted text-xs mt-0.5">{r.description}</div>}
              {r.prompt && <div className="text-faint text-xs mt-1 line-clamp-2 font-mono">{r.prompt}</div>}
            </div>
            <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition">
              <button onClick={() => setEditing(r.id)} className="btn p-1.5" aria-label="Edit"><Pencil className="w-3.5 h-3.5" /></button>
              <button onClick={() => onDelete(r.id)} className="btn p-1.5 text-bad hover:text-bad" aria-label="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        ),
      )}

      {adding ? (
        <Editor onSave={async (data) => { await onCreate(data); setAdding(false) }} onCancel={() => setAdding(false)} />
      ) : (
        <button onClick={() => setAdding(true)} className="btn w-full py-2.5 text-sm flex items-center justify-center gap-2">
          <Plus className="w-4 h-4" /> New recipe
        </button>
      )}

      {!adding && (
        <div className="pt-1">
          <div className="flex items-center gap-1.5 text-faint text-[11px] uppercase tracking-wide mb-1.5"><Sparkles className="w-3.5 h-3.5" /> Starters</div>
          <div className="flex flex-wrap gap-1.5">
            {STARTERS.filter((s) => !recipes.some((r) => r.name === s.name)).map((s) => (
              <button key={s.name} onClick={() => onCreate(s)} title={s.description}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-line/15 text-xs text-muted hover:text-fg hover:border-line/30 transition">
                <span>{s.emoji}</span> {s.name} <Plus className="w-3 h-3 opacity-60" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
