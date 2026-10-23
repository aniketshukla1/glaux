import React, { useRef, useState } from 'react'
import { LayoutDashboard, Info, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import Markdown from './Markdown.jsx'

// Generative Canvas (A2UI): render a sanitized UI spec the swarm produced. Every
// block type is an explicit, safe renderer — unknown types were already dropped
// server-side, so there's nothing to execute here.

const SERIES_COLORS = ['rgb(var(--accent))', 'rgb(var(--accent2))', '#fbbf24', '#fb7185', '#34d399', '#a78bfa']

const CALLOUT = {
  info: { Icon: Info, cls: 'border-accent/30 bg-accent/8 text-accent' },
  success: { Icon: CheckCircle2, cls: 'border-ok/30 bg-ok/8 text-ok' },
  warn: { Icon: AlertTriangle, cls: 'border-warn/30 bg-warn/8 text-warn' },
  danger: { Icon: XCircle, cls: 'border-bad/30 bg-bad/8 text-bad' },
}

function Callout({ tone = 'info', text }) {
  const { Icon, cls } = CALLOUT[tone] || CALLOUT.info
  return (
    <div className={`flex items-start gap-2 p-3 rounded-lg border text-sm ${cls}`}>
      <Icon className="w-4 h-4 mt-0.5 shrink-0" />
      <span className="text-fg/90">{text}</span>
    </div>
  )
}

function Metrics({ items = [] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
      {items.map((m, i) => (
        <div key={i} className="card p-3">
          <div className="text-faint text-xs truncate">{m.label}</div>
          <div className="text-fg text-xl font-semibold mt-1 truncate">{m.value}</div>
          {m.delta != null && <div className={`text-xs mt-0.5 ${String(m.delta).startsWith('-') ? 'text-bad' : 'text-ok'}`}>{m.delta}</div>}
        </div>
      ))}
    </div>
  )
}

function Table({ columns = [], rows = [] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line/15">
      <table className="w-full text-[12.5px] border-collapse">
        <thead>
          <tr>{columns.map((c, i) => <th key={i} className="text-left bg-line/8 text-fg font-medium px-2.5 py-1.5 border-b border-line/15">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-line/4">
              {(Array.isArray(r) ? r : []).map((cell, j) => <td key={j} className="px-2.5 py-1.5 border-b border-line/8 text-muted align-top">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Chart({ kind = 'bar', labels = [], series = [] }) {
  const W = 520, H = 180, padL = 30, padB = 24, padT = 10, padR = 10
  const iw = W - padL - padR, ih = H - padT - padB
  const max = Math.max(1, ...series.flatMap((s) => (s.data || []).map((v) => Number(v) || 0)))
  const x = (i) => padL + (labels.length > 1 ? (i * iw) / (labels.length - 1) : iw / 2)
  const xBand = (i) => padL + (i * iw) / Math.max(labels.length, 1)
  const y = (v) => padT + ih - (Math.max(0, Number(v) || 0) / max) * ih
  const band = iw / Math.max(labels.length, 1)

  const ref = useRef(null)
  const [hover, setHover] = useState(null) // { i, px, py }
  const onMove = (i) => (e) => {
    const r = ref.current?.getBoundingClientRect()
    if (r) setHover({ i, px: e.clientX - r.left, py: e.clientY - r.top })
  }

  return (
    <div className="relative" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
        <line x1={padL} y1={padT + ih} x2={W - padR} y2={padT + ih} stroke="rgb(var(--line))" strokeOpacity="0.25" />
        {hover && <rect x={xBand(hover.i)} y={padT} width={band} height={ih} fill="rgb(var(--fg))" fillOpacity="0.05" />}
        {kind === 'line' ? (
          <>
            {series.map((s, si) => (
              <polyline key={si} fill="none" stroke={SERIES_COLORS[si % SERIES_COLORS.length]} strokeWidth="2"
                points={(s.data || []).map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
            ))}
            {series.map((s, si) => (s.data || []).map((v, i) => (
              <circle key={`${si}-${i}`} cx={x(i)} cy={y(v)} r={hover?.i === i ? 4 : 2.5}
                fill={SERIES_COLORS[si % SERIES_COLORS.length]} stroke="rgb(var(--surface))" strokeWidth="1.5" />
            )))}
          </>
        ) : (
          labels.map((_, i) => {
            const bw = (band * 0.7) / Math.max(series.length, 1)
            const x0 = xBand(i) + band * 0.15
            return series.map((s, si) => {
              const v = (s.data || [])[i] || 0
              return <rect key={`${i}-${si}`} x={x0 + si * bw} y={y(v)} width={Math.max(1, bw - 2)} height={padT + ih - y(v)}
                rx="2" fill={SERIES_COLORS[si % SERIES_COLORS.length]} fillOpacity={hover && hover.i !== i ? 0.55 : 1} />
            })
          })
        )}
        {labels.map((l, i) => (
          <text key={i} x={kind === 'line' ? x(i) : xBand(i) + band / 2} y={H - 6} textAnchor="middle" fontSize="9" fill="rgb(var(--faint))">{l}</text>
        ))}
        {/* invisible hover bands per column */}
        {labels.map((_, i) => (
          <rect key={`hb${i}`} x={xBand(i)} y={padT} width={band} height={ih} fill="transparent"
            onMouseMove={onMove(i)} onMouseLeave={() => setHover(null)} />
        ))}
      </svg>
      {hover && (
        <div className="absolute z-10 pointer-events-none card px-2.5 py-1.5 shadow-xl text-xs whitespace-nowrap"
          style={{ left: hover.px, top: hover.py, transform: 'translate(-50%, calc(-100% - 10px))' }}>
          <div className="text-faint mb-1">{labels[hover.i]}</div>
          {series.map((s, si) => (
            <div key={si} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }} />
              <span className="text-muted">{s.name || `Series ${si + 1}`}</span>
              <span className="text-fg font-medium ml-auto pl-3">{(s.data || [])[hover.i]}</span>
            </div>
          ))}
        </div>
      )}
      {series.length > 1 && (
        <div className="flex flex-wrap gap-3 mt-1 px-1">
          {series.map((s, si) => (
            <span key={si} className="flex items-center gap-1.5 text-xs text-muted">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }} /> {s.name || `Series ${si + 1}`}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Block({ b }) {
  switch (b.type) {
    case 'heading': {
      const lvl = Math.min(3, Math.max(1, b.level || 2))
      const cls = lvl === 1 ? 'text-base' : lvl === 2 ? 'text-[15px]' : 'text-sm'
      return <div className={`text-fg font-semibold ${cls}`}>{b.text}</div>
    }
    case 'text': return <div className="text-fg text-[13.5px]"><Markdown>{b.text || ''}</Markdown></div>
    case 'callout': return <Callout tone={b.tone} text={b.text} />
    case 'metric': return <Metrics items={b.items} />
    case 'table': return <Table columns={b.columns} rows={b.rows} />
    case 'list': {
      const Tag = b.ordered ? 'ol' : 'ul'
      return <Tag className={`pl-5 space-y-1 text-fg text-[13.5px] ${b.ordered ? 'list-decimal' : 'list-disc'}`}>{(b.items || []).map((it, i) => <li key={i}>{it}</li>)}</Tag>
    }
    case 'code':
      return (
        <pre className="rounded-lg border border-line/15 bg-[#0d1117] text-[12.5px] leading-relaxed p-3 overflow-x-auto">
          <code className="text-[#c9d1d9]">{b.code || ''}</code>
        </pre>
      )
    case 'chart': return <Chart kind={b.kind} labels={b.labels} series={b.series} />
    case 'divider': return <hr className="border-line/15" />
    default: return null
  }
}

export default function Canvas({ spec }) {
  if (!spec || !Array.isArray(spec.blocks) || spec.blocks.length === 0) return null
  return (
    <div className="mt-4 rounded-xl border border-accent/20 bg-accent/[0.03] overflow-hidden">
      <div className="flex items-center gap-2 px-3.5 py-2 border-b border-line/10">
        <LayoutDashboard className="w-3.5 h-3.5 text-accent" />
        <span className="text-faint text-[11px] uppercase tracking-wide">Canvas</span>
        {spec.title && <span className="text-fg text-sm font-medium">· {spec.title}</span>}
      </div>
      <div className="p-3.5 space-y-3.5">
        {spec.blocks.map((b, i) => <Block key={i} b={b} />)}
      </div>
    </div>
  )
}
