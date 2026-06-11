import React, { useState } from 'react'

export default function TaskConsole({ onDispatch, loading, onReset }) {
  const [directive, setDirective] = useState(
    'Build a function that reverses a string and summarize how it works',
  )
  const [maxCalls, setMaxCalls] = useState('')
  const [maxUsd, setMaxUsd] = useState('')

  const submit = (e) => {
    e.preventDefault()
    if (!directive.trim()) return
    const budget = {}
    if (maxCalls) budget.max_llm_calls = Number(maxCalls)
    if (maxUsd) budget.max_usd = Number(maxUsd)
    onDispatch(directive.trim(), Object.keys(budget).length ? budget : null)
  }

  return (
    <form onSubmit={submit} className="glass p-4 space-y-3">
      <div className="flex gap-3 items-center">
        <span className="text-athena-accent text-lg">⚡</span>
        <input
          value={directive}
          onChange={(e) => setDirective(e.target.value)}
          placeholder="Dispatch a directive to the swarm…"
          className="flex-1 bg-transparent outline-none text-slate-200 placeholder-slate-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-athena-accent/20 border border-athena-accent/40 text-athena-accent hover:bg-athena-accent/30 disabled:opacity-50 transition"
        >
          {loading ? 'Running…' : 'Dispatch'}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="px-3 py-2 rounded-lg border border-slate-600/40 text-slate-400 hover:text-slate-200 transition"
        >
          Reset
        </button>
      </div>
      <div className="flex gap-3 items-center text-xs text-slate-500 pl-8">
        <span>budget (optional):</span>
        <label className="flex items-center gap-1">
          max LLM calls
          <input
            type="number"
            min="1"
            value={maxCalls}
            onChange={(e) => setMaxCalls(e.target.value)}
            placeholder="∞"
            className="w-16 bg-slate-800/40 rounded px-2 py-1 outline-none text-slate-300"
          />
        </label>
        <label className="flex items-center gap-1">
          max $
          <input
            type="number"
            step="0.01"
            min="0"
            value={maxUsd}
            onChange={(e) => setMaxUsd(e.target.value)}
            placeholder="∞"
            className="w-20 bg-slate-800/40 rounded px-2 py-1 outline-none text-slate-300"
          />
        </label>
      </div>
    </form>
  )
}
