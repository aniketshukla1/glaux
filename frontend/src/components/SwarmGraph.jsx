import React, { useMemo } from 'react'
import { ROLE_META, roleColor, buildSwarmGraph } from '../lib/blocks.js'

// Live view of the swarm: agents as orbs, hand-offs as edges with a capability
// token travelling along them. Built straight from the signed blocks — the
// swarm that actually did the work, not an illustration of one.

const VB_W = 560
const R = 16
const ROW = 58   // vertical spacing between specialists
const PAD = 30   // top padding; labels sit below each orb

function layout(nodes) {
  const specialists = nodes.filter((n) => n.id !== 'router' && n.id !== 'reflector')
  const n = Math.max(specialists.length, 1)
  const colH = (n - 1) * ROW
  const height = Math.max(104, colH + PAD * 2 + 18)
  const mid = PAD + colH / 2
  const pos = { router: { x: 80, y: mid } }
  specialists.forEach((s, i) => { pos[s.id] = { x: VB_W / 2, y: PAD + i * ROW } })
  if (nodes.some((x) => x.id === 'reflector')) pos.reflector = { x: VB_W - 80, y: mid }
  return { pos, height }
}

function edgePath(a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy) || 1
  const x1 = a.x + (dx / len) * R
  const y1 = a.y + (dy / len) * R
  const x2 = b.x - (dx / len) * R
  const y2 = b.y - (dy / len) * R
  const mx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
}

function Node({ node, p }) {
  const meta = ROLE_META[node.role] || ROLE_META.agent
  const c = roleColor(node.role)
  const working = node.status === 'working'
  const verified = (node.status === 'verified' || node.status === 'done') && node.id !== 'router'
  const revising = node.status === 'revising'
  const ring = revising ? 'rgb(var(--warn))' : verified ? 'rgb(var(--ok))' : c
  return (
    <g>
      <title>{`${meta.label}${meta.sub ? ` — ${meta.sub}` : ''} · ${node.status}`}</title>
      {working && (
        <circle cx={p.x} cy={p.y} r={R} style={{ fill: 'none', stroke: c }} strokeWidth="1.5">
          <animate attributeName="r" from={R} to={R + 13} dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" from="0.55" to="0" dur="1.6s" repeatCount="indefinite" />
        </circle>
      )}
      <circle cx={p.x} cy={p.y} r={R} style={{ fill: c, fillOpacity: 0.13, stroke: ring }} strokeWidth="1.5"
        strokeDasharray={revising ? '3 3' : undefined} />
      <circle cx={p.x} cy={p.y} r="4.5" style={{ fill: c }}>
        {working && <animate attributeName="r" values="4;6;4" dur="1.2s" repeatCount="indefinite" />}
      </circle>
      {verified && (
        <g transform={`translate(${p.x + R - 4}, ${p.y - R + 4})`}>
          <circle r="6" style={{ fill: 'rgb(var(--surface))', stroke: 'rgb(var(--ok))' }} strokeWidth="1.25" />
          <path d="M -2.4 0 L -0.6 1.9 L 2.6 -1.9" fill="none" style={{ stroke: 'rgb(var(--ok))' }} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      )}
      <text x={p.x} y={p.y + R + 13} textAnchor="middle" fontSize="11" fontWeight="550"
        style={{ fill: 'rgb(var(--muted))' }}>{meta.label}</text>
    </g>
  )
}

function Edge({ a, b, color, active }) {
  const d = edgePath(a, b)
  return (
    <g>
      <path d={d} fill="none" style={{ stroke: color }} strokeOpacity={active ? 0.65 : 0.28} strokeWidth={active ? 1.75 : 1.25}
        strokeDasharray={active ? '5 7' : undefined}>
        {active && <animate attributeName="stroke-dashoffset" from="24" to="0" dur="0.9s" repeatCount="indefinite" />}
      </path>
      {active && (
        <circle r="3" style={{ fill: color }}>
          <animateMotion dur="1.3s" repeatCount="indefinite" path={d} />
        </circle>
      )}
    </g>
  )
}

export default function SwarmGraph({ blocks, roleOf, running }) {
  const graph = useMemo(() => buildSwarmGraph(blocks || [], roleOf, { running }), [blocks, roleOf, running])
  const { pos, height } = useMemo(() => layout(graph.nodes), [graph])
  if (graph.nodes.length < 2) return null

  return (
    <svg viewBox={`0 0 ${VB_W} ${height}`} className="w-full block" style={{ maxHeight: height * 1.15 }}
      role="img" aria-label={`Swarm of ${graph.nodes.length} agents`}>
      {graph.edges.map((e, i) => {
        const a = pos[e.from]
        const b = pos[e.to]
        if (!a || !b) return null
        const role = graph.nodes.find((n) => n.id === e.to)?.role
        return <Edge key={i} a={a} b={b} color={roleColor(role)} active={e.active} />
      })}
      {graph.nodes.map((n) => pos[n.id] && <Node key={n.id} node={n} p={pos[n.id]} />)}
    </svg>
  )
}
