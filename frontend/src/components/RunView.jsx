import React, { useMemo, useRef, useState } from 'react'
import {
  ArrowUp, Compass, Code2, Search, ShieldCheck, Wrench, Terminal,
  Check, AlertTriangle, ChevronRight, Loader2, GraduationCap, BadgeCheck,
  Coins, Cpu, Mic, Volume2, VolumeX,
} from 'lucide-react'
import AthenaMark from './AthenaMark.jsx'
import SwarmGraph from './SwarmGraph.jsx'
import { ROLE_META, short, buildTimeline } from '../lib/blocks.js'
import { recognitionSupported, createRecognizer, ttsSupported, speak, stopSpeaking } from '../lib/speech.js'

const ROLE_ICON = { router: Compass, coder: Code2, researcher: Search, reflector: ShieldCheck, agent: Cpu }
const ACT_ICON = { tool: Wrench, skill: Terminal, check: Check, alert: AlertTriangle }

const EXAMPLES = [
  'Compute the sum of 5, 17 and 100',
  'Reverse a string and explain how it works',
  'Summarize how transformers work',
  'What is 12% of 4,500?',
]

function Avatar({ role }) {
  const meta = ROLE_META[role] || ROLE_META.agent
  const Icon = ROLE_ICON[role] || Cpu
  return (
    <div className="w-8 h-8 rounded-full grid place-items-center shrink-0"
      style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}44` }}>
      <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
    </div>
  )
}

function ProofView({ blocks }) {
  return (
    <div className="mt-3 pl-12 space-y-1.5 animate-fade-in">
      {blocks.map((b) => (
        <div key={b.index} className="flex items-center gap-2 text-xs">
          <span className="text-faint w-7">#{b.index}</span>
          <span className="text-muted font-mono">{b.action_type}</span>
          <span className="hash ml-auto">sig {short(b.signature)}</span>
        </div>
      ))}
    </div>
  )
}

function StepCard({ step, working }) {
  const [proof, setProof] = useState(false)
  const meta = ROLE_META[step.role] || ROLE_META.agent
  const status = working ? 'working' : step.verdict === 'retry' ? 'revising' : 'verified'
  return (
    <div className="card p-3.5 animate-fade-up">
      <div className="flex items-center gap-2.5">
        <Avatar role={step.role} />
        <div className="min-w-0">
          <div className="text-fg text-sm font-medium leading-tight">{meta.label}</div>
          <div className="text-faint text-xs">{meta.sub}</div>
        </div>
        <span className="ml-auto">
          {status === 'working' && <span className="flex items-center gap-1.5 text-xs text-accent"><Loader2 className="w-3.5 h-3.5 animate-spin" /> working</span>}
          {status === 'verified' && <span className="flex items-center gap-1.5 text-xs text-emerald-400"><BadgeCheck className="w-3.5 h-3.5" /> verified</span>}
          {status === 'revising' && <span className="flex items-center gap-1.5 text-xs text-amber-400"><AlertTriangle className="w-3.5 h-3.5" /> revising</span>}
        </span>
      </div>
      {(step.activities.length > 0 || working) && (
        <div className="mt-3 pl-12 space-y-2">
          {step.activities.map((a, i) => {
            const Icon = ACT_ICON[a.icon] || Check
            return (
              <div key={i} className="flex items-start gap-2.5 text-sm">
                <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${a.ok ? 'text-muted' : 'text-rose-400'}`} />
                <div className="min-w-0">
                  <span className="text-fg">{a.text}</span>
                  {a.detail && <span className="text-faint font-mono text-xs ml-2">{a.detail}</span>}
                </div>
              </div>
            )
          })}
          {working && step.activities.length === 0 && <div className="shimmer h-4 w-40 rounded bg-line/10" />}
        </div>
      )}
      {step.learned && (
        <div className="mt-3 ml-12 inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-accent2/10 border border-accent2/30 text-accent2">
          <GraduationCap className="w-3.5 h-3.5" /> learned a new skill: {step.learned}
        </div>
      )}
      <button onClick={() => setProof((v) => !v)} className="mt-3 ml-12 flex items-center gap-1 text-xs text-faint hover:text-muted transition">
        <ShieldCheck className="w-3.5 h-3.5" /> proof
        <ChevronRight className={`w-3.5 h-3.5 transition ${proof ? 'rotate-90' : ''}`} />
      </button>
      {proof && <ProofView blocks={step.blocks} />}
    </div>
  )
}

function PlanCard({ item }) {
  return (
    <div className="card p-3.5 animate-fade-up">
      <div className="flex items-center gap-2.5">
        <Compass className="w-3.5 h-3.5 text-accent2" />
        <span className="text-fg text-[13px]">Athena planned {item.steps.length} step{item.steps.length === 1 ? '' : 's'}</span>
        <div className="flex gap-1.5 ml-auto flex-wrap">
          {item.steps.map((s) => (
            <span key={s.id} className="text-xs px-2 py-0.5 rounded-md bg-line/8 text-muted">{(ROLE_META[s.role] || ROLE_META.agent).label}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

function ResultCard({ result, verification }) {
  const ok = result.success
  const c = result.cost || {}
  const [speaking, setSpeaking] = useState(false)
  const canSpeak = ttsSupported() && !!result.final
  const toggleSpeak = () => {
    if (speaking) { stopSpeaking(); setSpeaking(false); return }
    if (speak(result.final, { onEnd: () => setSpeaking(false) })) setSpeaking(true)
  }
  return (
    <div className="card p-4 animate-fade-up" style={{ borderColor: ok ? 'rgb(var(--accent) / 0.4)' : undefined }}>
      <div className="flex items-center gap-2 mb-1.5">
        <BadgeCheck className={`w-4 h-4 ${ok ? 'text-accent' : 'text-amber-400'}`} />
        <span className="text-faint text-[11px] uppercase tracking-wide">{ok ? 'Result' : 'Incomplete'}</span>
        {canSpeak && (
          <button onClick={toggleSpeak} className="ml-auto btn p-1" aria-label={speaking ? 'Stop reading' : 'Read aloud'} title={speaking ? 'Stop reading' : 'Read aloud'}>
            {speaking ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
      <p className="text-fg text-[13.5px] leading-relaxed">{result.final || '—'}</p>
      {result.budget_halt && <div className="mt-2 text-xs text-amber-400">budget guard: {result.budget_halt}</div>}
      <div className="mt-4 pt-3 border-t border-line/10 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        {verification?.valid && <span className="flex items-center gap-1.5 text-emerald-400"><ShieldCheck className="w-3.5 h-3.5" /> chain verified</span>}
        <span className="flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> {c.llm_calls || 0} model calls</span>
        <span>{(c.total_tokens || 0).toLocaleString()} tokens</span>
        <span className="flex items-center gap-1.5"><Coins className="w-3.5 h-3.5" /> ~${(c.usd || 0).toFixed(4)}</span>
      </div>
    </div>
  )
}

function DirectiveBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-md px-3 py-1.5 bg-accent/10 border border-accent/20 text-fg text-[13px] leading-relaxed">
        {text}
      </div>
    </div>
  )
}

// One run rendered as a conversation turn: the directive, the swarm timeline, the result.
function Turn({ directive, blocks, roleOf, running, result, verification }) {
  const timeline = useMemo(() => buildTimeline(blocks || [], roleOf), [blocks, roleOf])
  const lastStepIdx = (() => {
    for (let i = timeline.length - 1; i >= 0; i--) if (timeline[i].kind === 'step') return i
    return -1
  })()
  return (
    <div className="space-y-3">
      <DirectiveBubble text={directive} />
      <SwarmGraph blocks={blocks} roleOf={roleOf} running={running} />
      {timeline.map((item, i) =>
        item.kind === 'plan' ? <PlanCard key={item.index} item={item} />
          : item.kind === 'step' ? <StepCard key={item.index} step={item} working={running && i === lastStepIdx && !item.verdict} />
            : null,
      )}
      {running && timeline.length === 0 && (
        <div className="card p-4 flex items-center gap-3 animate-fade-in">
          <Loader2 className="w-4 h-4 animate-spin text-accent" />
          <span className="text-muted text-sm">Athena is planning…</span>
        </div>
      )}
      {result && <ResultCard result={result} verification={verification} />}
    </div>
  )
}

function Composer({ onDispatch, hero }) {
  const [input, setInput] = useState('')
  const [listening, setListening] = useState(false)
  const recRef = useRef(null)
  const submit = (e) => { e.preventDefault(); if (input.trim()) { onDispatch(input.trim()); setInput('') } }
  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return }
    const rec = createRecognizer({
      onResult: (text, isFinal) => { setInput(text); if (isFinal && text.trim()) { rec.stop(); onDispatch(text.trim()); setInput('') } },
      onError: () => setListening(false),
      onEnd: () => setListening(false),
    })
    if (!rec) return
    recRef.current = rec; setListening(true); rec.start()
  }
  return (
    <form onSubmit={submit} className={hero ? 'w-full max-w-2xl mt-7' : 'w-full'}>
      <div className="glass flex items-center gap-1.5 p-1.5 pl-3.5 rounded-xl">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={listening ? 'Listening…' : hero ? 'e.g. summarize how transformers work' : 'Ask Athena to do something…'}
          className="flex-1 bg-transparent outline-none text-fg text-sm placeholder-faint py-1.5"
          autoFocus={hero}
        />
        {recognitionSupported() && (
          <button type="button" onClick={toggleMic}
            className={`p-2 rounded-lg border transition ${listening ? 'border-rose-500/50 text-rose-400 bg-rose-500/10 animate-pulse' : 'border-line/16 text-muted hover:text-fg'}`}
            aria-label={listening ? 'Stop dictation' : 'Dictate'} title={listening ? 'Stop' : 'Speak your task'}>
            <Mic className="w-4 h-4" />
          </button>
        )}
        <button type="submit" disabled={!input.trim()} className="btn-accent p-2 disabled:opacity-40" aria-label="Run">
          <ArrowUp className="w-4 h-4" />
        </button>
      </div>
    </form>
  )
}

export default function RunView({ session, blocks, roleOf, running, result, goal, onDispatch, verification }) {
  const runs = session?.runs || []
  const liveTurn = running || result || (blocks && blocks.length > 0)
  const hasContent = runs.length > 0 || liveTurn

  if (!hasContent) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center text-center animate-fade-in px-5">
        <div className="w-11 h-11 rounded-2xl bg-accent/12 border border-accent/25 grid place-items-center mb-5">
          <AthenaMark className="w-7 h-7" />
        </div>
        <h1 className="text-fg text-2xl font-medium tracking-tight">What should Athena do?</h1>
        <p className="text-muted text-sm mt-2.5 max-w-md">Describe a goal. A swarm of agents plans it, does it, and proves every step.</p>
        <Composer onDispatch={onDispatch} hero />
        <div className="flex flex-wrap justify-center gap-2 mt-5 max-w-2xl">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => onDispatch(ex)} className="text-xs px-3 py-1.5 rounded-full border border-line/15 text-muted hover:text-fg hover:border-line/30 transition">{ex}</button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-[calc(100vh-3.5rem)]">
      <div className="flex-1 w-full max-w-5xl mx-auto px-5 sm:px-8 pt-4 pb-6 space-y-6">
        {runs.map((run) => (
          <Turn key={run.id} directive={run.directive} blocks={run.blocks} roleOf={roleOf}
            result={{ success: run.success, final: run.final, cost: run.cost }} verification={run.verification} />
        ))}
        {liveTurn && (
          <Turn directive={goal} blocks={blocks} roleOf={roleOf} running={running} result={result} verification={verification} />
        )}
      </div>
      <div className="sticky bottom-0 w-full max-w-5xl mx-auto px-5 sm:px-8 pb-5 pt-3 bg-gradient-to-t from-[rgb(var(--bg))] via-[rgb(var(--bg))] to-transparent">
        <Composer onDispatch={onDispatch} />
      </div>
    </div>
  )
}
