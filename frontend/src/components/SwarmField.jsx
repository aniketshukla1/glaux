import React, { useEffect, useRef } from 'react'

// A full-bleed ambient background that tells Glaux's story: a living swarm of faint
// nodes that drift and connect, with "signals" gliding along edges (agents handing
// off work — the destination node flashes when one arrives) and rare "seals" (a block
// being signed to the ledger). Pure canvas, no deps. Theme-aware (reads --accent /
// --accent2), honours prefers-reduced-motion, pauses when the tab is hidden, and is
// purely decorative (pointer-events-none, aria-hidden).

export default function SwarmField({ className = '', density = 1, opacity = 1 }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const LINK = 132 // px: nodes within this distance are linked
    const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`

    let W = 0, H = 0
    let nodes = [], signals = [], seals = []
    const colors = { a: [45, 212, 191], b: [129, 140, 248] }

    const readColors = () => {
      const css = getComputedStyle(document.documentElement)
      const parse = (v) => {
        const arr = v.trim().split(/[\s,]+/).map(Number)
        return arr.length === 3 && arr.every((n) => !Number.isNaN(n)) ? arr : null
      }
      colors.a = parse(css.getPropertyValue('--accent')) || colors.a
      colors.b = parse(css.getPropertyValue('--accent2')) || colors.b
    }

    const seed = () => {
      const rect = canvas.getBoundingClientRect()
      W = Math.max(1, Math.round(rect.width))
      H = Math.max(1, Math.round(rect.height))
      canvas.width = W * dpr
      canvas.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const N = Math.max(24, Math.min(90, Math.round((W * H) / 20000) * density))
      nodes = Array.from({ length: N }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.12, vy: (Math.random() - 0.5) * 0.12,
        r: 0.8 + Math.random() * 1.4, ph: Math.random() * Math.PI * 2,
        flash: 0, k: Math.random() < 0.34 ? 'a' : 'b',
      }))
      signals = []
      seals = []
    }

    const nearestNeighbor = (i) => {
      let best = -1, bd = LINK * LINK
      for (let j = 0; j < nodes.length; j++) {
        if (j === i) continue
        const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y
        const d = dx * dx + dy * dy
        if (d < bd) { bd = d; best = j }
      }
      return best
    }

    let raf, t = 0, lastSig = 0, lastSeal = 0

    const frame = (now) => {
      t += 0.016
      ctx.clearRect(0, 0, W, H)
      ctx.globalAlpha = opacity

      for (const n of nodes) {
        n.x += n.vx; n.y += n.vy
        if (n.x < -20) n.x = W + 20; else if (n.x > W + 20) n.x = -20
        if (n.y < -20) n.y = H + 20; else if (n.y > H + 20) n.y = -20
        if (n.flash > 0) n.flash *= 0.9
      }

      // proximity links
      ctx.lineWidth = 1
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK * LINK) {
            const a = (1 - Math.sqrt(d2) / LINK) * 0.14
            ctx.strokeStyle = rgba(colors.b, a)
            ctx.beginPath(); ctx.moveTo(nodes[i].x, nodes[i].y); ctx.lineTo(nodes[j].x, nodes[j].y); ctx.stroke()
          }
        }
      }

      // a new signal glides along a near edge
      if (!reduce && now - lastSig > 520 && signals.length < 7 && nodes.length > 2) {
        lastSig = now
        const i = (Math.random() * nodes.length) | 0
        const j = nearestNeighbor(i)
        if (j >= 0) signals.push({ i, j, t: 0, sp: 0.006 + Math.random() * 0.006 })
      }
      for (let s = signals.length - 1; s >= 0; s--) {
        const sg = signals[s]
        sg.t += sg.sp
        const A = nodes[sg.i], B = nodes[sg.j]
        const dx = B.x - A.x, dy = B.y - A.y
        if (sg.t >= 1 || dx * dx + dy * dy > (LINK * 1.8) ** 2) {
          if (sg.t >= 1) nodes[sg.j].flash = 1 // arrival: destination lights up
          signals.splice(s, 1); continue
        }
        const x = A.x + dx * sg.t, y = A.y + dy * sg.t
        const glow = ctx.createRadialGradient(x, y, 0, x, y, 7)
        glow.addColorStop(0, rgba(colors.a, 0.9)); glow.addColorStop(1, rgba(colors.a, 0))
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill()
        ctx.fillStyle = rgba(colors.a, 0.95); ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2); ctx.fill()
      }

      // a rare "seal" — a block signed to the ledger
      if (!reduce && now - lastSeal > 2600 && seals.length < 3 && nodes.length) {
        lastSeal = now
        const n = nodes[(Math.random() * nodes.length) | 0]
        seals.push({ x: n.x, y: n.y, t: 0 })
      }
      for (let s = seals.length - 1; s >= 0; s--) {
        const sl = seals[s]
        sl.t += 0.02
        if (sl.t >= 1) { seals.splice(s, 1); continue }
        ctx.strokeStyle = rgba(colors.b, (1 - sl.t) * 0.4)
        ctx.lineWidth = 1.2
        ctx.beginPath(); ctx.arc(sl.x, sl.y, 3 + sl.t * 26, 0, Math.PI * 2); ctx.stroke()
      }

      // nodes (twinkle + arrival flash)
      for (const n of nodes) {
        const tw = 0.6 + 0.4 * Math.sin(t * 1.6 + n.ph)
        const c = n.k === 'a' ? colors.a : colors.b
        ctx.fillStyle = rgba(c, 0.28 + tw * 0.34 + n.flash * 0.5)
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r + n.flash * 1.6, 0, Math.PI * 2); ctx.fill()
      }

      ctx.globalAlpha = 1
      raf = requestAnimationFrame(frame)
    }

    const start = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame) }
    const stop = () => cancelAnimationFrame(raf)

    readColors()
    seed()
    if (reduce) frame(0) // a single static frame
    else start()

    const onVis = () => { if (document.hidden) stop(); else if (!reduce) start() }
    const ro = new ResizeObserver(seed)
    ro.observe(canvas)
    const obs = new MutationObserver(readColors)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    document.addEventListener('visibilitychange', onVis)

    return () => {
      stop()
      ro.disconnect()
      obs.disconnect()
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [density, opacity])

  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none select-none ${className}`} />
}
