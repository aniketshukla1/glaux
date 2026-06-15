import React from 'react'

const MODES = [
  { key: 'auto', label: 'auto', cls: 'text-fg border-line/20 bg-line/10' },
  { key: 'gated', label: 'gated', cls: 'text-violet-300 border-violet-500/40 bg-violet-500/10' },
]

export default function ApprovalControl({ mode, onChange }) {
  return (
    <div className="flex items-center gap-1" title="HITL gate: in 'gated' mode, synthesized skills need human approval">
      <span className="text-xs text-faint mr-1">approval</span>
      {MODES.map((m) => (
        <button
          key={m.key}
          onClick={() => onChange(m.key)}
          className={`px-2 py-1 rounded text-xs border transition ${
            mode === m.key ? m.cls : 'text-faint border-line/15 hover:text-fg'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
