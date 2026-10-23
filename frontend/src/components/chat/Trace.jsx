import React, { useEffect, useMemo, useState } from 'react'
import {
  Compass, Code2, Search, ShieldCheck, Wrench, Terminal, Check, AlertTriangle, ChevronRight,
  Loader2, GraduationCap, Globe, FlaskConical, BarChart3, Server, Bug, PenLine, Cpu, ArrowUpRight,
} from 'lucide-react'
import SwarmGraph from '../SwarmGraph.jsx'
import { ROLE_META, roleColor, short, summarizeRun } from '../../lib/blocks.js'
import { BRAND } from '../../lib/brand.js'

export const ROLE_ICON = {
  router: Compass, coder: Code2, researcher: Search, reflector: ShieldCheck,
  web: Globe, scientist: FlaskConical, analyst: BarChart3, engineer: Server, tester: Bug, writer: PenLine,
  agent: Cpu,
}
const ACT_ICON = { tool: Wrench, skill: Terminal, check: Check, alert: AlertTriangle }

export function RoleDot({ role, size = 20, ring }) {
  const Icon = ROLE_ICON[role] || Cpu
  const c = roleColor(role)
  return (
    <span className="rounded-full grid place-items-center shrink-0"
      style={{ width: size, height: size, background: `color-mix(in oklab, ${c} 16%, rgb(var(--surface)))`, boxShadow: ring ? `0 0 0 2px rgb(var(--bg))` : undefined }}>
      <Icon style={{ width: size * 0.55, height: size * 0.55, color: c }} />
    </span>
  )
}

function list(names) {
  if (names.length <= 2) return names.join(' & ')
  return `${names.slice(0, -1).join(', ')} & ${names[names.length - 1]}`
}

function Step({ step, working, last }) {
  const meta = ROLE_META[step.role] || ROLE_META.agent
  const status = working ? 'working' : step.verdict === 'retry' ? 'revising' : 'verified'
  return (
    <li className="relative pl-7">
      {!last && <span className="absolute left-[9px] top-6 bottom-0 w-px bg-line/[0.12]" aria-hidden="true" />}
      <span className="absolute left-0 top-0.5"><RoleDot role={step.role} /></span>
      <div className="flex items-center gap-2 min-h-[22px]">
        <span className="text-[13px] text-fg font-medium">{meta.label}</span>
        <span className="text-[12px] text-faint truncate">{meta.sub}</span>
        <span className="ml-auto shrink-0">
          {status === 'working' && <span className="flex items-center gap-1 text-[11.5px] text-accent"><Loader2 className="w-3 h-3 animate-spin" /> working</span>}
          {status === 'verified' && <span className="flex items-center gap-1 text-[11.5px] text-ok"><Check className="w-3 h-3" /> verified</span>}
          {status === 'revising' && <span className="flex items-center gap-1 text-[11.5px] text-warn"><AlertTriangle className="w-3 h-3" /> revised</span>}
        </span>
      </div>
      <div className="pb-3">
        {step.activities.map((a, i) => {
          const Icon = ACT_ICON[a.icon] || Check
          return (
            <div key={i} className="flex items-start gap-2 text-[12.5px] mt-1">
              <Icon className={`w-3.5 h-3.5 mt-[2px] shrink-0 ${a.ok ? 'text-faint' : 'text-bad'}`} />
              <span className="min-w-0">
                <span className="text-muted">{a.text}</span>
                {a.detail && <span className="text-faint ml-1.5 break-words">{a.detail}</span>}
              </span>
            </div>
          )
        })}
        {working && step.activities.length === 0 && <div className="mt-1.5 shimmer h-3 w-40 rounded bg-line/[0.08]" />}
        {step.learned && (
          <span className="mt-1.5 inline-flex items-center gap-1.5 chip !border-accent2/30 !text-accent2 bg-accent2/[0.07]">
            <GraduationCap className="w-3 h-3" /> learned a new skill: <span className="font-medium">{step.learned}</span>
          </span>
        )}
      </div>
    </li>
  )
}

function Blocks({ blocks, roleOf, onOpenProof }) {
  return (
    <div className="mt-1 rounded-md border border-line/[0.08] bg-bg/50 overflow-hidden">
      <div className="max-h-56 overflow-y-auto divide-y divide-line/[0.06]">
        {blocks.map((b) => (
          <div key={b.index} className="flex items-center gap-3 px-3 py-1.5 text-[11.5px]">
            <span className="text-faint tabular-nums w-8 shrink-0">#{b.index}</span>
            <span className="mono text-muted w-36 shrink-0 truncate">{b.action_type}</span>
            <span className="text-faint truncate">{(ROLE_META[roleOf(b.agent_id)] || ROLE_META.agent).label}</span>
            <span className="hash ml-auto shrink-0">sig {short(b.signature || b.hash)}</span>
          </div>
        ))}
      </div>
      {onOpenProof && (
        <button onClick={() => onOpenProof(blocks.map((b) => b.index))}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11.5px] text-muted hover:text-fg border-t border-line/[0.08] hover:bg-line/[0.04]">
          Inspect in Proof <ArrowUpRight className="w-3 h-3" />
        </button>
      )}
    </div>
  )
}

// The swarm behind an answer, folded into one line. Open while it runs so you
// can watch it work; collapsed once the answer lands so the answer leads.
export default function Trace({ blocks, roleOf, running, verified, onOpenProof }) {
  const run = useMemo(() => summarizeRun(blocks, roleOf), [blocks, roleOf])
  const [open, setOpen] = useState(!!running)
  const [showBlocks, setShowBlocks] = useState(false)
  useEffect(() => { if (running) setOpen(true) }, [running])
  useEffect(() => { if (!running && blocks?.length) setOpen(false) }, [running]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!running && !blocks?.length) return null
  const steps = run.timeline.filter((i) => i.kind === 'step')
  const lastIdx = steps.length - 1
  const plan = run.timeline.find((i) => i.kind === 'plan')
  const names = run.roles.map((r) => (ROLE_META[r] || ROLE_META.agent).label)
  const current = running && steps.length ? steps[lastIdx] : null

  let summary
  if (running) {
    summary = current
      ? <><span className="text-fg">{(ROLE_META[current.role] || ROLE_META.agent).label}</span> is working<span className="text-faint"> — {(ROLE_META[current.role] || ROLE_META.agent).sub}</span></>
      : <span className="text-fg">Planning the team…</span>
  } else {
    summary = names.length
      ? <><span className="text-fg">{list(names)}</span>{run.steps.length > 0 && <span className="text-faint"> · {run.steps.length} step{run.steps.length === 1 ? '' : 's'}</span>}</>
      : <span className="text-fg">Answered directly</span>
  }

  return (
    <div className="animate-fade-in">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="group w-full flex items-center gap-2.5 py-1 text-left text-[12.5px] text-muted">
        <span className="flex -space-x-1.5 shrink-0">
          {running && !run.roles.length
            ? <span className="w-5 h-5 grid place-items-center"><Loader2 className="w-3.5 h-3.5 animate-spin text-accent" /></span>
            : run.roles.slice(0, 4).map((r) => <RoleDot key={r} role={r} ring />)}
        </span>
        <span className="truncate">{summary}</span>
        {!running && run.learned.length > 0 && (
          <span className="hidden sm:inline-flex items-center gap-1 text-accent2 shrink-0"><GraduationCap className="w-3 h-3" /> learned {run.learned.length}</span>
        )}
        <span className={`ml-auto shrink-0 flex items-center gap-1 tabular-nums ${verified === false ? 'text-bad' : 'text-faint'}`}
          title={`${run.signed} signed blocks`}>
          {running ? <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" /> : <ShieldCheck className={`w-3.5 h-3.5 ${verified === false ? '' : 'text-ok'}`} />}
          {run.signed} signed
        </span>
        <ChevronRight className={`w-3.5 h-3.5 shrink-0 text-faint transition-transform group-hover:text-muted ${open ? 'rotate-90' : ''}`} />
      </button>

      {open && (
        <div className="mt-1.5 mb-1 rounded-lg border border-line/[0.08] bg-surface/60 p-3 animate-fade-in">
          {run.roles.length > 0 && <div className="-mt-1 mb-2"><SwarmGraph blocks={blocks} roleOf={roleOf} running={running} /></div>}
          {plan && (
            <div className="flex items-center gap-2 mb-2.5 text-[12.5px] text-muted">
              <Compass className="w-3.5 h-3.5 text-accent2 shrink-0" />
              {BRAND} planned {plan.steps.length} step{plan.steps.length === 1 ? '' : 's'}
              <span className="text-faint truncate">
                · {plan.steps.map((s) => (ROLE_META[s.role] || ROLE_META.agent).label).join(' → ')}
              </span>
            </div>
          )}
          {running && steps.length === 0 && (
            <div className="flex items-center gap-2 text-[12.5px] text-muted py-1"><Loader2 className="w-3.5 h-3.5 animate-spin text-accent" /> {BRAND} is planning the team…</div>
          )}
          <ol className="mt-1">
            {steps.map((s, i) => <Step key={s.index} step={s} last={i === lastIdx} working={running && i === lastIdx && !s.verdict} />)}
          </ol>
          {blocks?.length > 0 && (
            <div className="pt-2 border-t border-line/[0.07]">
              <button onClick={() => setShowBlocks((v) => !v)} aria-expanded={showBlocks}
                className="flex items-center gap-1.5 text-[12px] text-faint hover:text-muted">
                <ShieldCheck className="w-3.5 h-3.5" />
                {showBlocks ? 'Hide' : 'Show'} the {blocks.length} signed block{blocks.length === 1 ? '' : 's'}
                <ChevronRight className={`w-3 h-3 transition-transform ${showBlocks ? 'rotate-90' : ''}`} />
              </button>
              {showBlocks && <Blocks blocks={blocks} roleOf={roleOf} onOpenProof={onOpenProof} />}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
