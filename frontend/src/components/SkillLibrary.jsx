import React, { useEffect, useState } from 'react'
import { getSkills, synthesizeSkill, useSkill } from '../api.js'

const STATUS = {
  quarantined: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
  promoted: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
  deprecated: 'text-rose-300 border-rose-500/40 bg-rose-500/10',
}

export default function SkillLibrary() {
  const [skills, setSkills] = useState([])
  const [task, setTask] = useState('Reverse a string')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const load = async () => {
    try {
      setSkills((await getSkills()).skills)
    } catch {
      setSkills([])
    }
  }
  useEffect(() => {
    load()
  }, [])

  const onSynth = async (e) => {
    e.preventDefault()
    if (!task.trim()) return
    setBusy(true)
    setResult(null)
    try {
      setResult(await synthesizeSkill(task.trim()))
      await load()
    } finally {
      setBusy(false)
    }
  }

  const onUse = async (id, success) => {
    await useSkill(id, success)
    await load()
  }

  return (
    <section>
      <h2 className="text-slate-300 mb-3">⚒ Skill Library</h2>

      <form onSubmit={onSynth} className="flex gap-2 mb-2">
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describe a skill to synthesize…"
          className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-slate-200 placeholder-slate-500"
        />
        <button
          disabled={busy}
          className="px-3 py-2 rounded-lg border border-athena-accent/40 text-athena-accent text-sm hover:bg-athena-accent/10 disabled:opacity-50"
        >
          {busy ? 'Synthesizing…' : 'Synthesize'}
        </button>
      </form>

      {result && (
        <div
          className={`glass p-3 mb-3 text-xs border ${
            result.ok ? 'border-emerald-500/40' : 'border-rose-500/40'
          }`}
        >
          <div className={result.ok ? 'text-emerald-300' : 'text-rose-300'}>
            {result.ok ? '✓ synthesized + sandbox-tested' : `✗ rejected: ${result.reason}`}
          </div>
          {result.cap_violations?.length > 0 && (
            <div className="text-rose-300 mt-1">caps: {result.cap_violations.join('; ')}</div>
          )}
          {result.test_results?.length > 0 && (
            <div className="text-slate-400 mt-1">
              tests: {result.test_results.filter((t) => t.ok).length}/{result.test_results.length} passed
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-slate-500 mb-2">
        Synthesized skills are sandbox-tested, then <span className="text-amber-300">quarantined</span>{' '}
        → <span className="text-emerald-300">promoted</span> after repeated success.
      </p>

      <div className="space-y-2 max-h-[55vh] overflow-auto pr-1">
        {skills.length === 0 && (
          <div className="glass p-6 text-center text-slate-500 text-sm">
            No skills yet. Synthesize one above.
          </div>
        )}
        {skills.map((s) => (
          <div key={s.id} className="glass p-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`px-2 py-0.5 rounded text-xs border ${STATUS[s.status] || ''}`}>
                {s.status}
              </span>
              <span className="text-sm text-slate-200">{s.name}</span>
              <span className="text-xs text-slate-500">v{s.version}</span>
              <span className="ml-auto text-xs text-slate-400">
                {s.usage_count} uses · {(s.success_rate * 100).toFixed(0)}%
              </span>
            </div>
            {s.description && <div className="text-xs text-slate-500 mt-1">{s.description}</div>}
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => onUse(s.id, true)}
                className="px-2 py-1 rounded text-xs border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10"
              >
                record success
              </button>
              <button
                onClick={() => onUse(s.id, false)}
                className="px-2 py-1 rounded text-xs border border-rose-500/40 text-rose-300 hover:bg-rose-500/10"
              >
                record failure
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
