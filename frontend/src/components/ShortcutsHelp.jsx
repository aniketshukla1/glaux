import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Keyboard, X } from 'lucide-react'

const SHORTCUTS = [
  { keys: ['⌘', 'K'], label: 'Command palette' },
  { keys: ['⌘', 'B'], label: 'Toggle sidebar' },
  { keys: ['?'], label: 'This shortcuts panel' },
  { keys: ['Enter'], label: 'Send message' },
  { keys: ['⇧', 'Enter'], label: 'New line in message' },
  { keys: ['Esc'], label: 'Close dialog / panel' },
]

function Key({ k }) {
  return (
    <kbd className="px-1.5 py-0.5 rounded-md border border-line/20 bg-line/8 text-[11px] text-muted min-w-[22px] inline-block text-center">
      {k}
    </kbd>
  )
}

export default function ShortcutsHelp({ open, onClose }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[75] grid place-items-center p-5">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative card w-full max-w-sm p-5 animate-fade-up">
        <div className="flex items-center gap-2 mb-4">
          <Keyboard className="w-4 h-4 text-accent" />
          <h2 className="text-fg font-medium">Keyboard shortcuts</h2>
          <button onClick={onClose} className="ml-auto btn p-1.5" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-2.5">
          {SHORTCUTS.map((s) => (
            <div key={s.label} className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted">{s.label}</span>
              <span className="flex items-center gap-1">{s.keys.map((k, j) => <Key key={j} k={k} />)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  )
}
