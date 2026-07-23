"use client";

import { useEffect, useRef } from "react";

// The ambient swarm background: drifting nodes that link by proximity, signals that
// glide along edges (agents handing off work — the destination flashes on arrival),
// and rare "seal" rings (a block signed to the ledger). Same idea as the app.
export function SwarmField({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const LINK = 132;
    const A = [45, 212, 191];
    const B = [129, 140, 248];
    const rgba = (c: number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

    let W = 0;
    let H = 0;
    type Node = { x: number; y: number; vx: number; vy: number; r: number; ph: number; flash: number; k: number[] };
    type Sig = { a: number; b: number; t: number; sp: number };
    type Seal = { x: number; y: number; t: number };
    let nodes: Node[] = [];
    let sigs: Sig[] = [];
    let seals: Seal[] = [];
    let raf = 0;
    let t = 0;
    let lastSig = 0;
    let lastSeal = 0;

    const seed = () => {
      const r = canvas.getBoundingClientRect();
      W = Math.max(1, Math.round(r.width));
      H = Math.max(1, Math.round(r.height));
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const N = Math.max(24, Math.min(90, Math.round((W * H) / 20000)));
      nodes = Array.from({ length: N }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
        r: 0.8 + Math.random() * 1.4,
        ph: Math.random() * 6.28,
        flash: 0,
        k: Math.random() < 0.34 ? A : B,
      }));
      sigs = [];
      seals = [];
    };

    const near = (i: number) => {
      let best = -1;
      let bd = LINK * LINK;
      for (let j = 0; j < nodes.length; j++) {
        if (j === i) continue;
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d = dx * dx + dy * dy;
        if (d < bd) {
          bd = d;
          best = j;
        }
      }
      return best;
    };

    const frame = (now: number) => {
      t += 0.016;
      ctx.clearRect(0, 0, W, H);
      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < -20) n.x = W + 20;
        else if (n.x > W + 20) n.x = -20;
        if (n.y < -20) n.y = H + 20;
        else if (n.y > H + 20) n.y = -20;
        if (n.flash > 0) n.flash *= 0.9;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK * LINK) {
            ctx.strokeStyle = rgba(B, (1 - Math.sqrt(d2) / LINK) * 0.14);
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }
      if (!reduce && now - lastSig > 520 && sigs.length < 7 && nodes.length > 2) {
        lastSig = now;
        const a = (Math.random() * nodes.length) | 0;
        const b = near(a);
        if (b >= 0) sigs.push({ a, b, t: 0, sp: 0.006 + Math.random() * 0.006 });
      }
      for (let s = sigs.length - 1; s >= 0; s--) {
        const g = sigs[s];
        g.t += g.sp;
        const P = nodes[g.a];
        const Q = nodes[g.b];
        const dx = Q.x - P.x;
        const dy = Q.y - P.y;
        if (g.t >= 1 || dx * dx + dy * dy > (LINK * 1.8) ** 2) {
          if (g.t >= 1) nodes[g.b].flash = 1;
          sigs.splice(s, 1);
          continue;
        }
        const x = P.x + dx * g.t;
        const y = P.y + dy * g.t;
        const gr = ctx.createRadialGradient(x, y, 0, x, y, 7);
        gr.addColorStop(0, rgba(A, 0.9));
        gr.addColorStop(1, rgba(A, 0));
        ctx.fillStyle = gr;
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, 6.2832);
        ctx.fill();
        ctx.fillStyle = rgba(A, 0.95);
        ctx.beginPath();
        ctx.arc(x, y, 1.5, 0, 6.2832);
        ctx.fill();
      }
      if (!reduce && now - lastSeal > 2600 && seals.length < 3 && nodes.length) {
        lastSeal = now;
        const n = nodes[(Math.random() * nodes.length) | 0];
        seals.push({ x: n.x, y: n.y, t: 0 });
      }
      for (let s = seals.length - 1; s >= 0; s--) {
        const sl = seals[s];
        sl.t += 0.02;
        if (sl.t >= 1) {
          seals.splice(s, 1);
          continue;
        }
        ctx.strokeStyle = rgba(B, (1 - sl.t) * 0.4);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(sl.x, sl.y, 3 + sl.t * 26, 0, 6.2832);
        ctx.stroke();
      }
      for (const n of nodes) {
        const tw = 0.6 + 0.4 * Math.sin(t * 1.6 + n.ph);
        ctx.fillStyle = rgba(n.k, 0.28 + tw * 0.34 + n.flash * 0.5);
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r + n.flash * 1.6, 0, 6.2832);
        ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    };

    seed();
    if (reduce) frame(0);
    else raf = requestAnimationFrame(frame);

    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !reduce) raf = requestAnimationFrame(frame);
    };
    window.addEventListener("resize", seed);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", seed);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none select-none ${className}`} />;
}
