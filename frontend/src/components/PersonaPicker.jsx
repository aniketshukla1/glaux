import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, Check, Sparkles, SlidersHorizontal } from 'lucide-react'

// Pick the active chat's persona (a saved system prompt). Shown in the top bar.
export default function PersonaPicker({ personas = [], activeId, onPick, onManage }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const active = personas.find((p) => p.id === activeId)
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} title="Persona for this chat"
        className="hidden sm:flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-line/15 text-muted hover:text-fg hover:border-line/30 transition">
        {active ? <span className="text-sm leading-none">{active.emoji || '🧠'}</span> : <Sparkles className="w-3.5 h-3.5" />}
        <span className="max-w-[120px] truncate">{active ? active.name : 'Persona'}</span>
        <ChevronDown className="w-3 h-3 shrink-0" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1.5 w-60 card p-1.5 shadow-xl z-50 animate-fade-in">
          <button onClick={() => { onPick(null); setOpen(false) }}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-muted hover:text-fg hover:bg-line/8 transition">
            {!activeId ? <Check className="w-3.5 h-3.5 text-accent shrink-0" /> : <span className="w-3.5 shrink-0" />}
            <span className="text-faint">No persona</span>
          </button>
          {personas.map((p) => (
            <button key={p.id} onClick={() => { onPick(p.id); setOpen(false) }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-muted hover:text-fg hover:bg-line/8 transition">
              {p.id === activeId ? <Check className="w-3.5 h-3.5 text-accent shrink-0" /> : <span className="text-sm leading-none w-3.5 text-center shrink-0">{p.emoji || '🧠'}</span>}
              <span className="truncate">{p.name}</span>
            </button>
          ))}
          <div className="border-t border-line/10 mt-1 pt-1">
            <button onClick={() => { setOpen(false); onManage?.() }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-muted hover:text-fg hover:bg-line/8 transition">
              <SlidersHorizontal className="w-3.5 h-3.5 shrink-0" /> Manage personas…
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
