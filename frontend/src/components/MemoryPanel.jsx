import React, { useEffect, useState } from 'react'
import { addMemory, getMemory } from '../api.js'

const LAYERS = ['semantic', 'episodic', 'procedural']
const LAYER_HINT = {
  semantic: 'facts & context · ranked by similarity',
  episodic: 'task traces · ranked by recency',
  procedural: 'skills · ranked by success rate',
}

export default function MemoryPanel() {
  const [layer, setLayer] = useState('semantic')
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (l = layer, q = '') => {
    try {
      const d = await getMemory(l, q)
      setItems(d.items)
    } catch {
      setItems([])
    }
  }

  useEffect(() => {
    setQuery('')
    load(layer, '')
  }, [layer])

  const onAdd = async (e) => {
    e.preventDefault()
    if (!draft.trim()) return
    setBusy(true)
    try {
      await addMemory(layer, { text: draft.trim() })
      setDraft('')
      await load(layer, query)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2 className="text-fg mb-3 flex items-center gap-2">⛁ Memory</h2>

      <div className="flex gap-1 mb-3">
        {LAYERS.map((l) => (
          <button
            key={l}
            onClick={() => setLayer(l)}
            className={`px-3 py-1 rounded-lg text-xs border transition ${
              layer === l
                ? 'text-accent border-accent/40 bg-accent/10'
                : 'text-faint border-line/15 hover:text-fg'
            }`}
          >
            {l}
          </button>
        ))}
      </div>
      <p className="text-xs text-faint mb-3">{LAYER_HINT[layer]}</p>

      <form onSubmit={onAdd} className="flex gap-2 mb-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Add to ${layer} memory…`}
          className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
        />
        <button
          disabled={busy}
          className="px-3 py-2 rounded-lg border border-accent/40 text-accent text-sm hover:bg-accent/10 disabled:opacity-50"
        >
          Add
        </button>
      </form>

      <div className="flex gap-2 mb-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load(layer, query)}
          placeholder="Search…"
          className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
        />
        <button
          onClick={() => load(layer, query)}
          className="px-3 py-2 rounded-lg border border-line/15 text-muted text-sm hover:text-fg"
        >
          Search
        </button>
      </div>

      <div className="space-y-2 max-h-[55vh] overflow-auto pr-1">
        {items.length === 0 && (
          <div className="glass p-6 text-center text-faint text-sm">
            Nothing in {layer} memory yet.
          </div>
        )}
        {items.map((it) => (
          <div key={it.id} className="glass p-3">
            <div className="text-sm text-fg">{it.text}</div>
            <div className="flex justify-between mt-1">
              <span className="hash">{it.id.slice(0, 12)}…</span>
              {it.similarity > 0 && (
                <span className="text-xs text-accent">
                  {(it.similarity * 100).toFixed(0)}% match
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
