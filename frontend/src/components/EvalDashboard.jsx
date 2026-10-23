import React, { useEffect, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import { getEvalRuns, runEval } from '../api.js'

// A tiny pass-rate sparkline over the benchmark history.
function Sparkline({ runs = [], className = '' }) {
  if (runs.length < 2) return null
  const W = 120, H = 34, p = 3
  const pts = runs.map((r, i) => {
    const x = p + (i * (W - 2 * p)) / (runs.length - 1)
    const y = p + (1 - (r.pass_rate || 0)) * (H - 2 * p)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className={className} preserveAspectRatio="none">
      <polyline points={pts.join(' ')} fill="none" stroke="rgb(var(--accent))" strokeWidth="1.5"
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r="2.2" fill="rgb(var(--accent))" />
    </svg>
  )
}

export default function EvalDashboard() {
  const [run, setRun] = useState(null)
  const [lift, setLift] = useState(null)
  const [history, setHistory] = useState([])
  const [trend, setTrend] = useState(null) // capability lift over time
  const [busy, setBusy] = useState(false)

  const loadHistory = async () => {
    try {
      const d = await getEvalRuns()
      setHistory(d.runs || [])
      setTrend(d.lift || null)
    } catch {
      setHistory([])
      setTrend(null)
    }
  }
  useEffect(() => {
    loadHistory()
  }, [])

  const onRun = async () => {
    setBusy(true)
    try {
      const r = await runEval()
      setRun(r.run)
      setLift(r.lift)
      await loadHistory()
    } finally {
      setBusy(false)
    }
  }

  const pct = (x) => `${(x * 100).toFixed(0)}%`

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <p className="text-muted text-[13px]">Score the skill library against a fixed benchmark suite.</p>
        <button
          onClick={onRun}
          disabled={busy}
          className="px-3 py-2 rounded-lg border border-accent/40 text-accent text-sm hover:bg-accent/10 disabled:opacity-50"
        >
          {busy ? 'Running…' : 'Run benchmark'}
        </button>
      </div>

      {trend && (
        <div className="glass p-4 mb-3 border border-accent/20">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint mb-2">
            <TrendingUp className="w-3.5 h-3.5 text-accent" /> Capability lift over time
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-baseline gap-1.5">
              <span className="text-muted text-sm">{pct(trend.first_pass_rate)}</span>
              <span className="text-faint">→</span>
              <span className="text-fg text-2xl font-semibold">{pct(trend.last_pass_rate)}</span>
              <span className={`text-sm font-medium ${trend.delta >= 0 ? 'text-ok' : 'text-bad'}`}>
                {trend.delta >= 0 ? '+' : ''}{(trend.delta * 100).toFixed(0)} pts
              </span>
            </div>
            <Sparkline runs={history} className="ml-auto" />
          </div>
          <div className="text-xs text-faint mt-2">
            pass rate across {trend.runs} benchmark runs as the library grew{' '}
            <span className="text-muted">{trend.skills_first} → {trend.skills_last} learned skills</span>.
          </div>
        </div>
      )}

      {run && (
        <>
          <div className="glass p-4 mb-3">
            <div className="flex items-end gap-3">
              <span className="text-xl text-fg">{pct(run.pass_rate)}</span>
              <span className="text-sm text-muted mb-1">
                {run.passed}/{run.total} cases passed
              </span>
              {lift && history.length > 1 && lift.delta_pass_rate !== 0 && (
                <span
                  className={`text-sm mb-1 ml-auto ${
                    lift.delta_pass_rate > 0 ? 'text-ok' : 'text-bad'
                  }`}
                >
                  {lift.delta_pass_rate > 0 ? '▲' : '▼'} {pct(Math.abs(lift.delta_pass_rate))} vs last
                </span>
              )}
            </div>
            {lift && lift.newly_passing.length > 0 && (
              <div className="text-xs text-ok mt-2">
                newly passing: {lift.newly_passing.join(', ')}
              </div>
            )}
            {lift && lift.newly_failing.length > 0 && (
              <div className="text-xs text-bad mt-1">
                regressed: {lift.newly_failing.join(', ')}
              </div>
            )}
          </div>

          <div className="space-y-2 max-h-[45vh] overflow-auto pr-1">
            {run.cases.map((c) => (
              <div key={c.name} className="glass p-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className={c.passed ? 'text-ok' : 'text-bad'}>
                    {c.passed ? '✓' : '✗'}
                  </span>
                  <span className="text-fg">{c.name}</span>
                  <span className="ml-auto text-xs text-faint">
                    {c.duration_ms.toFixed(0)}ms
                  </span>
                </div>
                {!c.passed && (
                  <div className="text-xs text-faint mt-1 pl-6">
                    {c.error}
                    {c.got !== null && c.got !== undefined && (
                      <>
                        {' '}· expected <code>{JSON.stringify(c.expected)}</code>, got{' '}
                        <code>{JSON.stringify(c.got)}</code>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {!run && (
        <div className="glass p-6 text-center text-faint text-sm">
          Run the benchmark suite to score the skill library. Synthesize skills (Skills tab) and
          re-run to see lift.
        </div>
      )}

      {history.length > 1 && (
        <div className="mt-3 text-xs text-faint">
          history: {history.map((h) => pct(h.pass_rate)).join(' → ')}
        </div>
      )}
    </section>
  )
}
