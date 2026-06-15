import React, { useEffect, useState } from 'react'
import { getEvalRuns, runEval } from '../api.js'

export default function EvalDashboard() {
  const [run, setRun] = useState(null)
  const [lift, setLift] = useState(null)
  const [history, setHistory] = useState([])
  const [busy, setBusy] = useState(false)

  const loadHistory = async () => {
    try {
      setHistory((await getEvalRuns()).runs)
    } catch {
      setHistory([])
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
        <h2 className="text-fg">📊 Eval Dashboard</h2>
        <button
          onClick={onRun}
          disabled={busy}
          className="px-3 py-2 rounded-lg border border-accent/40 text-accent text-sm hover:bg-accent/10 disabled:opacity-50"
        >
          {busy ? 'Running…' : 'Run benchmark'}
        </button>
      </div>

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
                    lift.delta_pass_rate > 0 ? 'text-emerald-300' : 'text-rose-300'
                  }`}
                >
                  {lift.delta_pass_rate > 0 ? '▲' : '▼'} {pct(Math.abs(lift.delta_pass_rate))} vs last
                </span>
              )}
            </div>
            {lift && lift.newly_passing.length > 0 && (
              <div className="text-xs text-emerald-300 mt-2">
                newly passing: {lift.newly_passing.join(', ')}
              </div>
            )}
            {lift && lift.newly_failing.length > 0 && (
              <div className="text-xs text-rose-300 mt-1">
                regressed: {lift.newly_failing.join(', ')}
              </div>
            )}
          </div>

          <div className="space-y-2 max-h-[45vh] overflow-auto pr-1">
            {run.cases.map((c) => (
              <div key={c.name} className="glass p-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className={c.passed ? 'text-emerald-300' : 'text-rose-300'}>
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
