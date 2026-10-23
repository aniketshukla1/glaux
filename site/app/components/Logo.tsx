// Glaux — the swarm as a constellation in the shape of Athena's owl. Kept in
// step with frontend/src/components/GlauxMark.jsx: small sizes use the heavier
// cut so the hairlines don't blur.

const EDGES = "M12 12 L21 24 L32 29 L43 24 L52 12 M21 24 L16 38 L32 52 L48 38 L43 24";

type Dot = [number, number, number];
const CUTS: Record<"full" | "compact", { viewBox: string; edge: number; nodes: Dot[]; eyes: Dot[] }> = {
  full: {
    viewBox: "8 8 48 48",
    edge: 2,
    nodes: [[12, 12, 2.8], [52, 12, 2.8], [21, 24, 3.2], [43, 24, 3.2], [32, 29, 2.8], [16, 38, 2.8], [48, 38, 2.8], [32, 52, 3.2]],
    eyes: [[25, 37, 4.6], [39, 37, 4.6]],
  },
  compact: {
    viewBox: "6.5 6.5 51 51",
    edge: 4.2,
    nodes: [[12, 12, 4.2], [52, 12, 4.2], [21, 24, 4.6], [43, 24, 4.6], [32, 29, 4], [16, 38, 4], [48, 38, 4], [32, 52, 4.6]],
    eyes: [[24.5, 37, 5.8], [39.5, 37, 5.8]],
  },
};

export function Logo({ size = 28 }: { size?: number }) {
  const cut = CUTS[size <= 24 ? "compact" : "full"];
  return (
    <svg width={size} height={size} viewBox={cut.viewBox} aria-hidden="true">
      <path d={EDGES} fill="none" stroke="rgb(var(--accent))" strokeOpacity="0.55" strokeWidth={cut.edge}
        strokeLinecap="round" strokeLinejoin="round" />
      {cut.nodes.map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="rgb(var(--accent))" />)}
      {cut.eyes.map(([x, y, r]) => <circle key={`e-${x}`} cx={x} cy={y} r={r} fill="rgb(var(--accent2))" />)}
    </svg>
  );
}
