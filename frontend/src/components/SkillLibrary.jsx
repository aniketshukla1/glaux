import React, { useEffect, useState } from 'react'
import { Hammer, AlertTriangle, Check, X } from 'lucide-react'
import { approveSkill, getSkills, rejectSkill, synthesizeSkill, useSkill } from '../api.js'

const STATUS = {
  pending_approval: 'text-violet-300 border-violet-500/40 bg-violet-500/10',
  quarantined: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
  promoted: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
  deprecated: 'text-rose-300 border-rose-500/40 bg-rose-500/10',
  rejected: 'text-muted border-line/15 bg-line/8',
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

  const onApprove = async (id) => {
    await approveSkill(id)
    await load()
  }

  const onReject = async (id) => {
    await rejectSkill(id)
    await load()
  }

  return (
    <section>
      <h2 className="text-fg mb-3 flex items-center gap-2"><Hammer className="w-4 h-4 text-accent" /> Skill Library</h2>

      <form onSubmit={onSynth} className="flex gap-2 mb-2">
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describe a skill to synthesize…"
          className="flex-1 glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint"
        />
        <button
          disabled={busy}
          className="px-3 py-2 rounded-lg border border-accent/40 text-accent text-sm hover:bg-accent/10 disabled:opacity-50"
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
            <div className="text-muted mt-1">
              tests: {result.test_results.filter((t) => t.ok).length}/{result.test_results.length} passed
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-faint mb-2">
        Synthesized skills are sandbox-tested, then <span className="text-amber-300">quarantined</span>{' '}
        → <span className="text-emerald-300">promoted</span> after repeated success.
      </p>

      <div className="space-y-2 max-h-[55vh] overflow-auto pr-1">
        {skills.length === 0 && (
          <div className="glass p-6 text-center text-faint text-sm">
            No skills yet. Synthesize one above.
          </div>
        )}
        {skills.map((s) => (
          <div key={s.id} className="glass p-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`px-2 py-0.5 rounded text-xs border ${STATUS[s.status] || ''}`}>
                {s.status.replace('_', ' ')}
              </span>
              {s.sensitive && (
                <span className="px-2 py-0.5 rounded text-xs border border-amber-500/40 text-amber-300 inline-flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> sensitive
                </span>
              )}
              <span className="text-sm text-fg">{s.name}</span>
              <span className="text-xs text-faint">v{s.version}</span>
              <span className="ml-auto text-xs text-muted">
                {s.usage_count} uses · {(s.success_rate * 100).toFixed(0)}%
              </span>
            </div>
            {s.description && <div className="text-xs text-faint mt-1">{s.description}</div>}
            {s.status === 'pending_approval' ? (
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => onApprove(s.id)}
                  className="px-2 py-1 rounded text-xs border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 inline-flex items-center gap-1"
                >
                  <Check className="w-3 h-3" /> approve
                </button>
                <button
                  onClick={() => onReject(s.id)}
                  className="px-2 py-1 rounded text-xs border border-rose-500/40 text-rose-300 hover:bg-rose-500/10 inline-flex items-center gap-1"
                >
                  <X className="w-3 h-3" /> reject
                </button>
              </div>
            ) : (
              s.status !== 'rejected' && (
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
              )
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
