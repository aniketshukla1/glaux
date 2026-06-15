import React, { useEffect, useRef } from 'react'
import AthenaMark from './AthenaMark.jsx'

// Athena's owl, alive — the logo at the centre, breathing, wrapped in a slowly
// rotating constellation of swarm nodes (brand gradient, depth-shaded, pulsing).
// Pure canvas (no deps), theme-aware (reads --accent / --accent2).

function fibonacciSphere(n) {
  const pts = []
  const ga = Math.PI * (1 + Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = 1 - ((i + 0.5) / n) * 2
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const th = ga * i
    pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r })
  }
  return pts
}

export default function ConstellationSphere({ size = 300 }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.scale(dpr, dpr)

    const N = 66
    const pts = fibonacciSphere(N)
    const kind = pts.map((_, i) => (i % 3 === 0 ? 'a' : 'b')) // a = accent, b = accent2
    const phase = pts.map(() => Math.random() * Math.PI * 2)

    const edges = []
    const TH = 0.62
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y, dz = pts[i].z - pts[j].z
        if (dx * dx + dy * dy + dz * dz < TH * TH) edges.push([i, j])
      }
    }

    const colors = { a: [45, 212, 191], b: [129, 140, 248] }
    const readColors = () => {
      const css = getComputedStyle(document.documentElement)
      const parse = (v) => {
        const a = v.trim().split(/[\s,]+/).map(Number)
        return a.length === 3 && a.every((n) => !Number.isNaN(n)) ? a : null
      }
      colors.a = parse(css.getPropertyValue('--accent')) || colors.a
      colors.b = parse(css.getPropertyValue('--accent2')) || colors.b
    }
    readColors()
    const obs = new MutationObserver(readColors)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

    const cx = size / 2
    const cy = size / 2
    const R = size * 0.42
    const proj = new Array(N)
    let raf
    let t = 0

    const render = () => {
      t += 0.005
      ctx.clearRect(0, 0, size, size)

      const ay = t * 0.5
      const ax = Math.sin(t * 0.3) * 0.3
      const cosY = Math.cos(ay), sinY = Math.sin(ay)
      const cosX = Math.cos(ax), sinX = Math.sin(ax)

      for (let i = 0; i < N; i++) {
        const p = pts[i]
        const x1 = p.x * cosY + p.z * sinY
        const z1 = -p.x * sinY + p.z * cosY
        const y1 = p.y * cosX - z1 * sinX
        const z2 = p.y * sinX + z1 * cosX
        proj[i] = { sx: cx + x1 * R, sy: cy + y1 * R, depth: (z2 + 1.3) / 2.3, k: kind[i], idx: i }
      }

      // breathing central glow (behind the owl)
      const pulse = 1 + 0.06 * Math.sin(t * 1.3)
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5 * pulse)
      g.addColorStop(0, `rgba(${colors.b[0]},${colors.b[1]},${colors.b[2]},0.18)`)
      g.addColorStop(0.55, `rgba(${colors.a[0]},${colors.a[1]},${colors.a[2]},0.05)`)
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.fillRect(0, 0, size, size)

      ctx.lineWidth = 1
      for (let e = 0; e < edges.length; e++) {
        const a = proj[edges[e][0]]
        const b = proj[edges[e][1]]
        const d = (a.depth + b.depth) / 2
        if (d < 0.15) continue
        ctx.strokeStyle = `rgba(${colors.b[0]},${colors.b[1]},${colors.b[2]},${0.03 + d * 0.12})`
        ctx.beginPath()
        ctx.moveTo(a.sx, a.sy)
        ctx.lineTo(b.sx, b.sy)
        ctx.stroke()
      }

      proj.sort((p, q) => p.depth - q.depth)
      for (let i = 0; i < N; i++) {
        const p = proj[i]
        const c = p.k === 'a' ? colors.a : colors.b
        const np = 1 + 0.3 * Math.sin(t * 2.2 + phase[p.idx])
        const rr = (0.9 + p.depth * 1.8) * np
        ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${0.22 + p.depth * 0.62})`
        ctx.beginPath()
        ctx.arc(p.sx, p.sy, rr, 0, Math.PI * 2)
        ctx.fill()
      }

      raf = requestAnimationFrame(render)
    }
    render()

    return () => {
      cancelAnimationFrame(raf)
      obs.disconnect()
    }
  }, [size])

  const owl = Math.round(size * 0.32)
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <canvas ref={ref} className="absolute inset-0 pointer-events-none select-none" style={{ width: size, height: size }} aria-hidden="true" />
      <div className="relative animate-breathe" style={{ width: owl, height: owl, filter: 'drop-shadow(0 0 14px rgb(var(--accent) / 0.5))' }}>
        <AthenaMark className="w-full h-full" />
      </div>
    </div>
  )
}
