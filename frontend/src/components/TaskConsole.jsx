import React, { useState } from 'react'

export default function TaskConsole({ onDispatch, loading, onReset }) {
  const [directive, setDirective] = useState(
    'Build a function that reverses a string and summarize how it works',
  )

  const submit = (e) => {
    e.preventDefault()
    if (directive.trim()) onDispatch(directive.trim())
  }

  return (
    <form onSubmit={submit} className="glass p-4 flex gap-3 items-center">
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
    </form>
  )
}
