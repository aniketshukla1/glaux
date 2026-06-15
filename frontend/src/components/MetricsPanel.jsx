import React, { useEffect, useState } from 'react'
import { getMetrics } from '../api.js'

function Card({ label, value, sub }) {
  return (
    <div className="glass p-4">
      <div className="text-lg text-slate-100">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function MetricsPanel() {
  const [m, setM] = useState(null)

  const load = async () => {
    try {
      setM(await getMetrics())
    } catch {
      setM(null)
    }
  }
  useEffect(() => {
    load()
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [])

  if (!m) {
    return (
      <section>
        <h2 className="text-slate-300 mb-3">📈 Metrics</h2>
        <div className="glass p-6 text-center text-slate-500 text-sm">No metrics yet.</div>
      </section>
    )
  }

  const successPct = m.tasks_total ? ((m.tasks_success / m.tasks_total) * 100).toFixed(0) : '—'

  return (
    <section>
      <h2 className="text-slate-300 mb-3 flex items-center gap-2">
        📈 Metrics <span className="text-xs text-slate-500">(live · also at /metrics)</span>
      </h2>
      <div className="grid grid-cols-2 gap-3">
        <Card
          label="tasks dispatched"
          value={m.tasks_total}
          sub={`${successPct}% success · ${m.task_duration_avg_s}s avg`}
        />
        <Card
          label="task outcomes"
          value={`${m.tasks_success}✓ ${m.tasks_incomplete}~ ${m.tasks_budget_halt}⛔`}
          sub="success · incomplete · budget-halt"
        />
        <Card label="LLM calls" value={m.llm_calls} sub={`${m.tokens_total.toLocaleString()} tokens`} />
        <Card label="estimated spend" value={`$${m.usd_total.toFixed(4)}`} sub="across all tasks" />
        <Card label="skills synthesized" value={m.skills_synthesized} />
        <Card
          label="benchmark runs"
          value={m.eval_runs}
          sub={m.eval_runs ? `last pass rate ${(m.last_pass_rate * 100).toFixed(0)}%` : ''}
        />
      </div>
      <p className="text-xs text-slate-500 mt-3 leading-relaxed">
        Counters are exposed in Prometheus format at <code>/metrics</code>; every task and eval run
        also emits a structured JSON log line to stdout.
      </p>
    </section>
  )
}
