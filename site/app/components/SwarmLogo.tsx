"use client";

import { useEffect, useRef, useState } from "react";
import { Logo } from "./Logo";

const LOOP_MS = 12000;
const SLOW_FRAME_MS = 34;

// The logo made of light: a real-time 3D scene, in the same engine that renders the README's
// animation. It loads only where WebGL works, holds still for reduced motion, and pauses off screen.
export function SwarmLogo() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"loading" | "live" | "fallback">("loading");

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let disposed = false;
    let cleanup = () => {};

    const probe = document.createElement("canvas");
    if (!(probe.getContext("webgl2") || probe.getContext("webgl"))) {
      setState("fallback");
      return;
    }

    import("../lib/swarm-logo.js")
      .then(({ createSwarmLogo }) => {
        if (disposed) return;
        const small = window.matchMedia("(max-width: 767px)").matches;
        const logo = createSwarmLogo({
          canvas, mark: "glaux", scale: 1.5, galaxy: 1.75, background: 0x000000,
          density: small ? 0.5 : 1, bloom: !small, dust: small ? 160 : 420,
        });
        const fit = () => {
          const box = canvas.getBoundingClientRect();
          if (box.width) logo.resize(box.width, box.height, Math.min(window.devicePixelRatio || 1, 1.75));
        };
        fit();

        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          const still = () => { fit(); logo.render(0.1); };
          still();
          setState("live");
          window.addEventListener("resize", still);
          cleanup = () => { window.removeEventListener("resize", still); logo.dispose(); };
          return;
        }

        // Start just before the swarm collapses, so the reveal is the first thing a visitor sees.
        const start = performance.now() - 0.6 * LOOP_MS;
        let raf = 0;
        let visible = true;
        let px = 0, py = 0, x = 0, y = 0;
        let last = 0, slow = 0, seen = 0;
        const tick = (now: number) => {
          raf = 0;
          if (!visible) return;
          x += (px - x) * 0.06;
          y += (py - y) * 0.06;
          logo.render(((now - start) / LOOP_MS) % 1, { x, y });
          if (last && seen < 120) {   // a device that can't hold 30 fps loses the bloom, not the logo
            seen++;
            if (now - last > SLOW_FRAME_MS) slow++;
            if (seen === 120 && slow > 70) logo.setBloom(false);
          }
          last = now;
          raf = requestAnimationFrame(tick);
        };
        const onMove = (e: PointerEvent) => {
          px = (e.clientX / window.innerWidth - 0.5) * 0.5;
          py = (e.clientY / window.innerHeight - 0.5) * 0.3;
        };
        const resize = new ResizeObserver(fit);
        resize.observe(canvas);
        const watch = new IntersectionObserver(([entry]) => {
          visible = entry.isIntersecting;
          if (visible && !raf) { last = 0; raf = requestAnimationFrame(tick); }
        });
        watch.observe(canvas);
        window.addEventListener("pointermove", onMove, { passive: true });
        raf = requestAnimationFrame(tick);
        setState("live");
        cleanup = () => {
          cancelAnimationFrame(raf);
          resize.disconnect();
          watch.disconnect();
          window.removeEventListener("pointermove", onMove);
          logo.dispose();
        };
      })
      .catch(() => setState("fallback"));

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  if (state === "fallback") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Logo size={200} />
      </div>
    );
  }
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className={`h-full w-full transition-opacity duration-700 ${state === "live" ? "opacity-100" : "opacity-0"}`}
      style={{
        // Black plus screen blending: the canvas adds its light to the page and nothing else.
        mixBlendMode: "screen",
        maskImage: "radial-gradient(closest-side, #000 70%, transparent 100%)",
        WebkitMaskImage: "radial-gradient(closest-side, #000 70%, transparent 100%)",
      }}
    />
  );
}
