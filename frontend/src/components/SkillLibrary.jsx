import React, { useEffect, useState } from 'react'
import { AlertTriangle, Check, X, Shield, ShieldCheck } from 'lucide-react'
import { approveSkill, getHealth, getSkills, rejectSkill, synthesizeSkill } from '../api.js'

// How skill code is isolated when it runs. WASM = the v2 no-ambient-authority
// backend (can't syscall at all); subprocess = the hardened child-process sandbox.
function SandboxBadge({ sandbox }) {
  if (!sandbox) return null
  const wasm = sandbox.active === 'wasm'
  const Icon = wasm ? ShieldCheck : Shield
  const label = wasm ? 'WASM isolation' : 'subprocess sandbox'
  const cls = wasm
    ? 'text-ok border-ok/40 bg-ok/10'
    : 'text-info border-info/40 bg-info/10'
  const title = wasm
    ? 'Skills run in a WebAssembly guest with no ambient authority (no syscalls by default).'
    : sandbox.wasm_runtime
      ? 'Hardened child-process sandbox. WASM v2 backend is available — set ATHENA_SANDBOX_BACKEND=auto + ATHENA_PYTHON_WASM to enable.'
      : 'Hardened child-process sandbox (network/filesystem/process guards + resource limits).'
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border ${cls}`}
      title={title}
    >
      <Icon className="w-3 h-3" /> {label}
    </span>
  )
}

const STATUS = {
  pending_approval: 'text-accent2 border-accent2/40 bg-accent2/10',
  quarantined: 'text-warn border-warn/40 bg-warn/10',
  promoted: 'text-ok border-ok/40 bg-ok/10',
  deprecated: 'text-bad border-bad/40 bg-bad/10',
  rejected: 'text-muted border-line/15 bg-line/8',
}

export default function SkillLibrary() {
  const [skills, setSkills] = useState([])
  const [task, setTask] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [sandbox, setSandbox] = useState(null)

  const load = async () => {
    try {
      setSkills((await getSkills()).skills)
    } catch {
      setSkills([])
    }
  }
  useEffect(() => {
    load()
    getHealth().then((h) => setSandbox(h.sandbox)).catch(() => setSandbox(null))
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
      <div className="flex items-center gap-2 mb-3">
        <span className="ml-auto"><SandboxBadge sandbox={sandbox} /></span>
      </div>

      <form onSubmit={onSynth} className="flex gap-2 mb-2">
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describe a skill to write, e.g. reverse a string"
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
            result.ok ? 'border-ok/40' : 'border-bad/40'
          }`}
        >
          <div className={result.ok ? 'text-ok' : 'text-bad'}>
            {result.ok ? '✓ synthesized + sandbox-tested' : `✗ rejected: ${result.reason}`}
          </div>
          {result.cap_violations?.length > 0 && (
            <div className="text-bad mt-1">caps: {result.cap_violations.join('; ')}</div>
          )}
          {result.test_results?.length > 0 && (
            <div className="text-muted mt-1">
              tests: {result.test_results.filter((t) => t.ok).length}/{result.test_results.length} passed
            </div>
          )}
        </div>
      )}

      <div className="space-y-2 mt-3">
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
                <span className="px-2 py-0.5 rounded text-xs border border-warn/40 text-warn inline-flex items-center gap-1">
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
                  className="px-2 py-1 rounded text-xs border border-ok/40 text-ok hover:bg-ok/10 inline-flex items-center gap-1"
                >
                  <Check className="w-3 h-3" /> approve
                </button>
                <button
                  onClick={() => onReject(s.id)}
                  className="px-2 py-1 rounded text-xs border border-bad/40 text-bad hover:bg-bad/10 inline-flex items-center gap-1"
                >
                  <X className="w-3 h-3" /> reject
                </button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}
