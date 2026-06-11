import React from 'react'

const MODES = [
  { key: 'live', label: '● live', cls: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10' },
  { key: 'dry_run', label: '◐ dry-run', cls: 'text-amber-300 border-amber-500/40 bg-amber-500/10' },
  { key: 'halted', label: '■ halted', cls: 'text-rose-300 border-rose-500/40 bg-rose-500/10' },
]

export default function SafetyControl({ mode, onChange }) {
  return (
    <div className="flex items-center gap-1" title="Global kill switch">
      <span className="text-xs text-slate-500 mr-1">safety</span>
      {MODES.map((m) => {
        const active = mode === m.key
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            className={`px-2 py-1 rounded text-xs border transition ${
              active ? m.cls : 'text-slate-500 border-slate-700/50 hover:text-slate-300'
            }`}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
