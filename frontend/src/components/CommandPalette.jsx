import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Search, Loader2 } from 'lucide-react'

// ⌘K: every action, every page, every conversation — and, through `search`,
// the text inside conversations too.
export default function CommandPalette({ open, onClose, commands, search }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [hits, setHits] = useState([])
  const [searching, setSearching] = useState(false)
  const listRef = useRef(null)

  useEffect(() => { if (open) { setQ(''); setHits([]) } }, [open])
  useEffect(() => {
    const s = q.trim()
    if (!open || !search || s.length < 2) { setHits([]); setSearching(false); return undefined }
    let live = true
    setSearching(true)
    const id = setTimeout(async () => {
      try { const r = await search(s); if (live) setHits(r) } catch { if (live) setHits([]) } finally { if (live) setSearching(false) }
    }, 180)
    return () => { live = false; clearTimeout(id) }
  }, [q, open, search])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    const local = s ? commands.filter((c) => `${c.label} ${c.keywords || ''} ${c.section || ''}`.toLowerCase().includes(s)) : commands
    const seen = new Set(local.map((c) => c.sessionId).filter(Boolean))
    return [...local, ...hits.filter((h) => !seen.has(h.sessionId))]
  }, [q, commands, hits])

  useEffect(() => { setSel(0) }, [q, open])
  useEffect(() => { listRef.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' }) }, [sel])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, filtered.length - 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)) }
      else if (e.key === 'Enter') { e.preventDefault(); const c = filtered[sel]; if (c) { c.run(); onClose() } }
      else if (e.key === 'Escape') { e.preventDefault(); onClose() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, filtered, sel, onClose])

  if (!open) return null
  let lastSection = null
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[13vh] p-4">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px] animate-fade-in" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="relative popover w-full max-w-xl overflow-hidden animate-pop-in">
        <div className="flex items-center gap-2.5 px-4 border-b border-line/[0.08]">
          {searching ? <Loader2 className="w-4 h-4 text-faint shrink-0 animate-spin" /> : <Search className="w-4 h-4 text-faint shrink-0" />}
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search commands and conversations"
            placeholder="Search conversations, pages and actions…"
            className="flex-1 bg-transparent outline-none focus-visible:outline-none text-fg text-[14px] py-3.5 placeholder:text-faint" />
          <span className="kbd">esc</span>
        </div>
        <div ref={listRef} role="listbox" className="max-h-[52vh] overflow-y-auto p-1.5">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-faint text-[13px]">{searching ? 'Searching…' : 'Nothing matches'}</div>
          ) : filtered.map((c, i) => {
            const header = c.section && c.section !== lastSection ? c.section : null
            lastSection = c.section
            return (
              <React.Fragment key={c.id}>
                {header && <div className="px-2.5 pt-2.5 pb-1 eyebrow">{header}</div>}
                <button data-i={i} role="option" aria-selected={i === sel} data-active={i === sel}
                  onMouseMove={() => sel !== i && setSel(i)} onClick={() => { c.run(); onClose() }}
                  className="menu-item !py-2">
                  {c.icon && <c.icon className="w-4 h-4 shrink-0 text-faint" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{c.label}</span>
                    {c.snippet && <span className="block truncate text-[11.5px] text-faint">{c.snippet}</span>}
                  </span>
                  {c.hint && <span className="text-faint text-[11.5px] shrink-0">{c.hint}</span>}
                </button>
              </React.Fragment>
            )
          })}
        </div>
      </div>
    </div>
  )
}
