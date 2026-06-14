import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'

export default function CommandPalette({ open, onClose, commands }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const listRef = useRef(null)

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return commands
    return commands.filter((c) => `${c.label} ${c.keywords || ''} ${c.section || ''}`.toLowerCase().includes(s))
  }, [q, commands])

  useEffect(() => { setSel(0) }, [q, open])
  useEffect(() => { if (open) setQ('') }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, filtered.length - 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)) }
      else if (e.key === 'Enter') { e.preventDefault(); const c = filtered[sel]; if (c) { c.run(); onClose() } }
      else if (e.key === 'Escape') { e.preventDefault(); onClose() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, filtered, sel, onClose])

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-i="${sel}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [sel])

  if (!open) return null

  let lastSection = null
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[14vh] p-5">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative card w-full max-w-xl overflow-hidden shadow-2xl">
        <div className="flex items-center gap-2.5 px-4 border-b border-line/10">
          <Search className="w-4 h-4 text-faint shrink-0" />
          <input
            autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Type a command or search…"
            className="flex-1 bg-transparent outline-none text-fg py-3.5 placeholder:text-faint"
          />
          <kbd className="text-[10px] text-faint border border-line/20 rounded px-1.5 py-0.5">esc</kbd>
        </div>
        <div ref={listRef} className="max-h-[52vh] overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-faint text-sm">No matching commands</div>
          ) : (
            filtered.map((c, i) => {
              const header = c.section && c.section !== lastSection ? c.section : null
              lastSection = c.section
              return (
                <React.Fragment key={c.id}>
                  {header && <div className="px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-faint">{header}</div>}
                  <button
                    data-i={i}
                    onMouseEnter={() => setSel(i)}
                    onClick={() => { c.run(); onClose() }}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition ${i === sel ? 'bg-accent/12 text-fg' : 'text-muted'}`}
                  >
                    {c.icon && <c.icon className="w-4 h-4 text-faint shrink-0" />}
                    <span className="flex-1 truncate">{c.label}</span>
                    {c.hint && <span className="text-faint text-xs shrink-0">{c.hint}</span>}
                  </button>
                </React.Fragment>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
