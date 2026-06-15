import React, { useState } from 'react'
import { Radio } from 'lucide-react'
import { getBlock } from '../api.js'

const COLORS = {
  PLAN: '#818cf8',
  CALL_AGENT: '#fbbf24',
  CAPABILITY_GRANT: '#34d399',
  CALL_SKILL: '#f472b6',
  THINK: '#94a3b8',
  EMIT_OBSERVATION: '#22d3ee',
  REFLECT: '#a78bfa',
}

const short = (s) => (s ? `${s.slice(0, 8)}…${s.slice(-4)}` : '')

function BlockCard({ b }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const color = COLORS[b.action_type] || '#64748b'

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && !detail) {
      try {
        setDetail(await getBlock(b.index))
      } catch {
        /* ignore */
      }
    }
  }

  return (
    <div className="glass p-3">
      <button onClick={toggle} className="w-full flex items-center gap-3 text-left">
        <span className="text-xs text-faint w-8 shrink-0">#{b.index}</span>
        <span
          className="px-2 py-0.5 rounded text-xs font-semibold shrink-0"
          style={{ background: `${color}22`, color }}
        >
          {b.action_type}
        </span>
        <span className="text-xs text-muted shrink-0">{short(b.agent_id)}</span>
        <span className="ml-auto hash">{short(b.hash)}</span>
        <span className="text-faint text-xs">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="mt-3 pl-11 text-xs space-y-2">
          <div>
            <span className="text-faint">payload</span>
            <pre className="whitespace-pre-wrap text-fg mt-1">
              {detail ? JSON.stringify(detail.payload, null, 2) : '…'}
            </pre>
          </div>
          {detail && <div className="hash">signature {short(detail.signature)}</div>}
          <div className="hash">prev {short(b.prev_hash)}</div>
        </div>
      )}
    </div>
  )
}

export default function SwarmFeed({ blocks, streaming }) {
  return (
    <section>
      <h2 className="text-fg mb-3 flex items-center gap-2">
        <Radio className="w-4 h-4 text-accent" /> Swarm Feed <span className="text-xs text-faint">({blocks.length} blocks)</span>
        {streaming && (
          <span className="text-xs text-emerald-300 flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            live
          </span>
        )}
      </h2>
      <div className="space-y-2 max-h-[70vh] overflow-auto pr-1">
        {blocks.length === 0 && (
          <div className="glass p-6 text-center text-faint">
            No activity yet. Dispatch a directive above.
          </div>
        )}
        {blocks.map((b) => (
          <BlockCard key={b.index} b={b} />
        ))}
      </div>
    </section>
  )
}
