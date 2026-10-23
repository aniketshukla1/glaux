import React from 'react'

// Glaux — the swarm drawn as a constellation in the shape of Athena's owl.
// Each node is an agent, each line a signed hand-off; the two bright points
// are the eyes. Hairlines blur below ~24px, so small sizes switch to a heavier
// cut of the same drawing: same nodes, thicker lines, bigger eyes.

const EDGES = 'M12 12 L21 24 L32 29 L43 24 L52 12 M21 24 L16 38 L32 52 L48 38 L43 24'

const CUTS = {
  full: {
    viewBox: '8 8 48 48',
    edge: 2,
    nodes: [[12, 12, 2.8], [52, 12, 2.8], [21, 24, 3.2], [43, 24, 3.2], [32, 29, 2.8], [16, 38, 2.8], [48, 38, 2.8], [32, 52, 3.2]],
    eyes: [[25, 37, 4.6], [39, 37, 4.6]],
  },
  compact: {
    viewBox: '6.5 6.5 51 51',
    edge: 4.2,
    nodes: [[12, 12, 4.2], [52, 12, 4.2], [21, 24, 4.6], [43, 24, 4.6], [32, 29, 4], [16, 38, 4], [48, 38, 4], [32, 52, 4.6]],
    eyes: [[24.5, 37, 5.8], [39.5, 37, 5.8]],
  },
}

export default function GlauxMark({ size = 24, mono = false, className = '', title }) {
  const cut = CUTS[size <= 24 ? 'compact' : 'full']
  const body = mono ? 'currentColor' : 'rgb(var(--accent))'
  const eye = mono ? 'currentColor' : 'rgb(var(--accent2))'
  return (
    <svg width={size} height={size} viewBox={cut.viewBox} className={className}
      role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <path d={EDGES} fill="none" stroke={body} strokeOpacity="0.55" strokeWidth={cut.edge}
        strokeLinecap="round" strokeLinejoin="round" />
      {cut.nodes.map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill={body} />)}
      {cut.eyes.map(([x, y, r]) => <circle key={`e-${x}`} cx={x} cy={y} r={r} fill={eye} />)}
    </svg>
  )
}
