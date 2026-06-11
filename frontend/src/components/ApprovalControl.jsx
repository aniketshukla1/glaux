import React from 'react'

const MODES = [
  { key: 'auto', label: 'auto', cls: 'text-slate-300 border-slate-500/50 bg-slate-700/30' },
  { key: 'gated', label: 'gated', cls: 'text-violet-300 border-violet-500/40 bg-violet-500/10' },
]

export default function ApprovalControl({ mode, onChange }) {
  return (
    <div className="flex items-center gap-1" title="HITL gate: in 'gated' mode, synthesized skills need human approval">
      <span className="text-xs text-slate-500 mr-1">approval</span>
      {MODES.map((m) => (
        <button
          key={m.key}
          onClick={() => onChange(m.key)}
          className={`px-2 py-1 rounded text-xs border transition ${
            mode === m.key ? m.cls : 'text-slate-500 border-slate-700/50 hover:text-slate-300'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
