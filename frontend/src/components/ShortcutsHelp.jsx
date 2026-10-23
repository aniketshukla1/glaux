import React, { useEffect } from 'react'
import { X, Keyboard } from 'lucide-react'

const SHORTCUTS = [
  { keys: ['⌘', 'K'], label: 'Search and commands' },
  { keys: ['⌘', 'B'], label: 'Collapse or expand the sidebar' },
  { keys: ['⌘', ','], label: 'Settings' },
  { keys: ['?'], label: 'This list' },
  { keys: ['Enter'], label: 'Send' },
  { keys: ['⇧', 'Enter'], label: 'New line' },
  { keys: ['/'], label: 'Commands and recipes, at the start of a message' },
  { keys: ['Esc'], label: 'Close a dialog or menu' },
]

export default function ShortcutsHelp({ open, onClose }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[75] grid place-items-center p-5">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px] animate-fade-in" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="relative popover w-full max-w-sm p-5 animate-pop-in">
        <div className="flex items-center gap-2 mb-3">
          <Keyboard className="w-4 h-4 text-accent" />
          <h2 className="text-fg font-medium text-[15px]">Keyboard shortcuts</h2>
          <button onClick={onClose} className="ml-auto btn-ghost p-1.5" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <ul className="divide-y divide-line/[0.07]">
          {SHORTCUTS.map((s) => (
            <li key={s.label} className="flex items-center justify-between gap-4 py-2 text-[13px]">
              <span className="text-muted">{s.label}</span>
              <span className="flex items-center gap-1 shrink-0">{s.keys.map((k) => <span key={k} className="kbd">{k}</span>)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
