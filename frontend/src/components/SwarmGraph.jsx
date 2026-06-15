import React, { useMemo } from 'react'
import { ROLE_META, buildSwarmGraph } from '../lib/blocks.js'

// Premium, live visualization of the swarm: agents as glowing orbs, hand-offs as
// edges with a capability token flowing along them, status rendered in real time.
// Built straight from the signed blocks — the swarm that actually did the work.

const VB_W = 600
const VB_H = 300
const R = 26

function layout(nodes) {
  const pos = {}
  const specialists = nodes.filter((n) => n.id !== 'router' && n.id !== 'reflector')
  const hasReflector = nodes.some((n) => n.id === 'reflector')
  pos.router = { x: VB_W / 2, y: 56 }
  const n = specialists.length
  const spread = Math.min(VB_W - 160, n * 150)
  const startX = VB_W / 2 - spread / 2 + spread / (2 * Math.max(n, 1))
  specialists.forEach((s, i) => {
    pos[s.id] = { x: n === 1 ? VB_W / 2 : startX + (i * spread) / n, y: VB_H / 2 + 6 }
  })
  if (hasReflector) pos.reflector = { x: VB_W / 2, y: VB_H - 64 }
  return pos
}

// A smooth cubic between two node centres, trimmed to the node edges.
function edgePath(a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy) || 1
  const ux = dx / len
  const uy = dy / len
  const x1 = a.x + ux * R
  const y1 = a.y + uy * R
  const x2 = b.x - ux * R
  const y2 = b.y - uy * R
  const my = (y1 + y2) / 2
  return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`
}

function Node({ node, p }) {
  const meta = ROLE_META[node.role] || ROLE_META.agent
  const c = meta.color
  const working = node.status === 'working'
  const verified = node.status === 'verified' || node.status === 'done'
  const revising = node.status === 'revising'
  const ring = revising ? '#fbbf24' : working ? c : verified ? '#34d399' : c
  return (
    <g>
      {working && (
        <circle cx={p.x} cy={p.y} r={R} fill="none" stroke={c} strokeWidth="2" opacity="0.6">
          <animate attributeName="r" from={R} to={R + 22} dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" from="0.55" to="0" dur="1.6s" repeatCount="indefinite" />
        </circle>
      )}
      <circle cx={p.x} cy={p.y} r={R} fill={c} fillOpacity="0.12" stroke={ring} strokeWidth="2"
        strokeDasharray={revising ? '4 4' : undefined} style={{ filter: working ? `drop-shadow(0 0 10px ${c}aa)` : 'none' }} />
      <circle cx={p.x} cy={p.y} r="7" fill={c}>
        {working && <animate attributeName="r" values="6;8.5;6" dur="1.2s" repeatCount="indefinite" />}
      </circle>
      {verified && node.id !== 'router' && (
        <g transform={`translate(${p.x + R - 8}, ${p.y - R + 8})`}>
          <circle r="8" fill="#0b0f17" stroke="#34d399" strokeWidth="1.5" />
          <path d="M -3.2 0 L -0.8 2.6 L 3.4 -2.6" fill="none" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      )}
      <text x={p.x} y={p.y + R + 16} textAnchor="middle" fontSize="13" fontWeight="600" fill="rgb(var(--fg))">{meta.label}</text>
      <text x={p.x} y={p.y + R + 30} textAnchor="middle" fontSize="10" fill="rgb(var(--faint))">{meta.sub}</text>
    </g>
  )
}

function Edge({ a, b, color, active }) {
  const d = edgePath(a, b)
  return (
    <g>
      <path d={d} fill="none" stroke={color} strokeOpacity={active ? 0.55 : 0.22} strokeWidth={active ? 2.5 : 1.5}
        strokeDasharray={active ? '6 8' : undefined}>
        {active && <animate attributeName="stroke-dashoffset" from="28" to="0" dur="0.9s" repeatCount="indefinite" />}
      </path>
      {active && (
        <circle r="4.5" fill={color} style={{ filter: `drop-shadow(0 0 6px ${color})` }}>
          <animateMotion dur="1.4s" repeatCount="indefinite" path={d} />
        </circle>
      )}
    </g>
  )
}

export default function SwarmGraph({ blocks, roleOf, running }) {
  const graph = useMemo(() => buildSwarmGraph(blocks || [], roleOf, { running }), [blocks, roleOf, running])
  const pos = useMemo(() => layout(graph.nodes), [graph])
  if (!graph.nodes.length) return null

  return (
    <div className="card p-3 overflow-hidden">
      <div className="flex items-center gap-2 mb-1 px-1">
        <span className="text-faint text-xs uppercase tracking-wide">Swarm</span>
        {running && (
          <span className="flex items-center gap-1 text-xs text-accent">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" /> live
          </span>
        )}
        <span className="ml-auto text-faint text-[11px]">{graph.nodes.length} agents · signed hand-offs</span>
      </div>
      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="w-full" style={{ maxHeight: 210 }}>
        <defs>
          <radialGradient id="swarm-bg" cx="50%" cy="38%" r="65%">
            <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity="0.06" />
            <stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect x="0" y="0" width={VB_W} height={VB_H} fill="url(#swarm-bg)" />
        {graph.edges.map((e, i) => {
          const a = pos[e.from]
          const b = pos[e.to]
          if (!a || !b) return null
          const color = (ROLE_META[graph.nodes.find((n) => n.id === e.to)?.role] || ROLE_META.agent).color
          return <Edge key={i} a={a} b={b} color={color} active={e.active} />
        })}
        {graph.nodes.map((n) => pos[n.id] && <Node key={n.id} node={n} p={pos[n.id]} />)}
      </svg>
    </div>
  )
}
