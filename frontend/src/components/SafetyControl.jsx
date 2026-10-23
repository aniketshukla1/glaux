import React from 'react'

const MODES = [
  { key: 'live', label: '● live', cls: 'text-ok border-ok/40 bg-ok/10' },
  { key: 'dry_run', label: '◐ dry-run', cls: 'text-warn border-warn/40 bg-warn/10' },
  { key: 'halted', label: '■ halted', cls: 'text-bad border-bad/40 bg-bad/10' },
]

export default function SafetyControl({ mode, onChange }) {
  return (
    <div className="flex items-center gap-1" title="Global kill switch">
      <span className="text-xs text-faint mr-1">safety</span>
      {MODES.map((m) => {
        const active = mode === m.key
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            className={`px-2 py-1 rounded text-xs border transition ${
              active ? m.cls : 'text-faint border-line/15 hover:text-fg'
            }`}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
