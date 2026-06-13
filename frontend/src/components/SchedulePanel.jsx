import React, { useCallback, useEffect, useState } from 'react'
import {
  CalendarClock, Plus, Play, Pause, Trash2, Zap, Clock, Loader2, CheckCircle2, AlertTriangle,
} from 'lucide-react'
import { getSchedules, addSchedule, removeSchedule, enableSchedule, runSchedule } from '../api.js'

const PRESETS = [
  { label: 'Every day 9am', spec: '0 9 * * *' },
  { label: 'Hourly', spec: '@hourly' },
  { label: 'Weekly (Sun)', spec: '@weekly' },
  { label: 'Every 30 min', spec: 'every 30m' },
]

const fmt = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function StatusBadge({ status }) {
  if (status === 'ok') return <span className="flex items-center gap-1 text-xs" style={{ color: 'rgb(52 211 153)' }}><CheckCircle2 className="w-3 h-3" /> ok</span>
  if (status === 'error') return <span className="flex items-center gap-1 text-xs" style={{ color: 'rgb(251 113 133)' }}><AlertTriangle className="w-3 h-3" /> error</span>
  if (status === 'running') return <span className="flex items-center gap-1 text-xs text-muted"><Loader2 className="w-3 h-3 animate-spin" /> running</span>
  return null
}

function JobRow({ job, onChanged }) {
  const [busy, setBusy] = useState(false)
  const act = async (fn) => { setBusy(true); try { await fn(job.id) } finally { setBusy(false); onChanged() } }
  return (
    <div className="card p-3">
      <div className="flex items-start gap-2">
        <span className="text-fg text-sm flex-1">{job.directive}</span>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => act(runSchedule)} disabled={busy} className="btn p-1.5" aria-label="Run now" title="Run now">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
          </button>
          <button onClick={() => act((id) => enableSchedule(id, !job.enabled))} disabled={busy} className="btn p-1.5" aria-label="Toggle" title={job.enabled ? 'Pause' : 'Resume'}>
            {job.enabled ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button onClick={() => act(removeSchedule)} disabled={busy} className="btn p-1.5" aria-label="Delete" title="Delete">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap mt-2 text-xs">
        <span className="px-1.5 py-0.5 rounded border border-line/15 text-muted font-mono">{job.schedule}</span>
        {!job.enabled && <span className="text-faint">paused</span>}
        <span className="text-faint flex items-center gap-1"><Clock className="w-3 h-3" /> next {fmt(job.next_run)}</span>
        {job.last_run && <span className="text-faint">· last {fmt(job.last_run)}</span>}
        <StatusBadge status={job.last_status} />
        {job.run_count > 0 && <span className="text-faint">· {job.run_count} run{job.run_count === 1 ? '' : 's'}</span>}
      </div>
      {job.last_result && (
        <div className="text-faint text-xs mt-1.5 line-clamp-2">{job.last_result}</div>
      )}
    </div>
  )
}

export default function SchedulePanel() {
  const [jobs, setJobs] = useState([])
  const [directive, setDirective] = useState('')
  const [schedule, setSchedule] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setJobs((await getSchedules()).jobs || [])
    } catch {
      setJobs([])
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [refresh])

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!directive.trim() || !schedule.trim()) return setErr('Directive and schedule are both required.')
    setBusy(true)
    try {
      await addSchedule(directive.trim(), schedule.trim())
      setDirective(''); setSchedule('')
      await refresh()
    } catch {
      // surface the backend's validation detail
      try {
        const r = await fetch('/api/schedules', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ directive: directive.trim(), schedule: schedule.trim() }),
        })
        const j = await r.json().catch(() => ({}))
        setErr(j.detail || 'Could not create the job.')
      } catch {
        setErr('Could not create the job.')
      }
    } finally {
      setBusy(false)
    }
  }

  const inputCls = 'w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint'

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <CalendarClock className="w-4 h-4 text-accent" />
        <h2 className="text-fg font-medium">Schedules</h2>
        <span className="text-faint text-xs">{jobs.length} job{jobs.length === 1 ? '' : 's'}</span>
      </div>

      <form onSubmit={submit} className="card p-3 space-y-2.5">
        <div className="flex items-center gap-2">
          <Plus className="w-4 h-4 text-accent" />
          <span className="text-fg text-sm font-medium">Schedule a recurring task</span>
        </div>
        <input value={directive} onChange={(e) => setDirective(e.target.value)} placeholder="what should the swarm do? (e.g. summarize today's commits)" className={inputCls} />
        <input value={schedule} onChange={(e) => setSchedule(e.target.value)} placeholder="cron (0 9 * * *), @daily, or every 30m" className={`${inputCls} font-mono`} />
        <div className="flex gap-1.5 flex-wrap">
          {PRESETS.map((p) => (
            <button key={p.spec} type="button" onClick={() => setSchedule(p.spec)} className="px-2 py-1 rounded-md text-xs border border-line/15 text-faint hover:text-muted">
              {p.label}
            </button>
          ))}
        </div>
        {err && <div className="text-xs whitespace-pre-wrap" style={{ color: 'rgb(251 113 133)' }}>{err}</div>}
        <button disabled={busy} className="btn-accent px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CalendarClock className="w-4 h-4" />}
          Schedule
        </button>
      </form>

      <div className="space-y-2">
        {jobs.length === 0 ? (
          <div className="card p-6 text-center text-faint text-sm">No scheduled jobs yet.</div>
        ) : (
          jobs.map((j) => <JobRow key={j.id} job={j} onChanged={refresh} />)
        )}
      </div>

      <p className="text-faint text-xs leading-relaxed">
        Jobs run the swarm unattended on their cadence — every run is signed onto the ledger just like a
        manual task. Schedules persist across restarts.
      </p>
    </section>
  )
}
