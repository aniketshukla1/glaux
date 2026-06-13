import React, { useMemo, useRef, useState } from 'react'
import {
  Sparkles, ArrowUp, Compass, Code2, Search, ShieldCheck, Wrench, Terminal,
  Check, AlertTriangle, ChevronRight, Loader2, GraduationCap, BadgeCheck,
  Plus, Coins, Cpu, Mic, Volume2, VolumeX,
} from 'lucide-react'
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
    <div
      className="w-9 h-9 rounded-full grid place-items-center shrink-0"
      style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}44` }}
    >
      <Icon className="w-4 h-4" style={{ color: meta.color }} />
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
    <div className="card p-4 animate-fade-up">
      <div className="flex items-center gap-3">
        <Avatar role={step.role} />
        <div className="min-w-0">
          <div className="text-fg font-medium leading-tight">{meta.label}</div>
          <div className="text-faint text-xs">{meta.sub}</div>
        </div>
        <span className="ml-auto">
          {status === 'working' && (
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> working
            </span>
          )}
          {status === 'verified' && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <BadgeCheck className="w-3.5 h-3.5" /> verified
            </span>
          )}
          {status === 'revising' && (
            <span className="flex items-center gap-1.5 text-xs text-amber-400">
              <AlertTriangle className="w-3.5 h-3.5" /> revising
            </span>
          )}
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
          {working && step.activities.length === 0 && (
            <div className="shimmer h-4 w-40 rounded bg-line/10" />
          )}
        </div>
      )}

      {step.learned && (
        <div className="mt-3 ml-12 inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-accent2/10 border border-accent2/30 text-accent2">
          <GraduationCap className="w-3.5 h-3.5" /> learned a new skill: {step.learned}
        </div>
      )}

      <button
        onClick={() => setProof((v) => !v)}
        className="mt-3 ml-12 flex items-center gap-1 text-xs text-faint hover:text-muted transition"
      >
        <ShieldCheck className="w-3.5 h-3.5" /> proof
        <ChevronRight className={`w-3.5 h-3.5 transition ${proof ? 'rotate-90' : ''}`} />
      </button>
      {proof && <ProofView blocks={step.blocks} />}
    </div>
  )
}

function PlanCard({ item }) {
  return (
    <div className="card p-4 animate-fade-up">
      <div className="flex items-center gap-2.5">
        <Compass className="w-4 h-4 text-accent2" />
        <span className="text-fg text-sm">
          Athena planned {item.steps.length} step{item.steps.length === 1 ? '' : 's'}
        </span>
        <div className="flex gap-1.5 ml-auto flex-wrap">
          {item.steps.map((s) => (
            <span key={s.id} className="text-xs px-2 py-0.5 rounded-md bg-line/8 text-muted">
              {(ROLE_META[s.role] || ROLE_META.agent).label}
            </span>
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
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
      return
    }
    if (speak(result.final, { onEnd: () => setSpeaking(false) })) setSpeaking(true)
  }
  return (
    <div className="card p-5 animate-fade-up" style={{ borderColor: ok ? 'rgb(var(--accent) / 0.4)' : undefined }}>
      <div className="flex items-center gap-2 mb-2">
        <BadgeCheck className={`w-5 h-5 ${ok ? 'text-accent' : 'text-amber-400'}`} />
        <span className="text-faint text-xs uppercase tracking-wide">{ok ? 'Result' : 'Incomplete'}</span>
        {canSpeak && (
          <button
            onClick={toggleSpeak}
            className="ml-auto btn p-1.5"
            aria-label={speaking ? 'Stop reading' : 'Read aloud'}
            title={speaking ? 'Stop reading' : 'Read aloud'}
          >
            {speaking ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
        )}
      </div>
      <p className="text-fg text-lg leading-relaxed">{result.final || '—'}</p>
      {result.budget_halt && (
        <div className="mt-2 text-xs text-amber-400">budget guard: {result.budget_halt}</div>
      )}
      <div className="mt-4 pt-3 border-t border-line/10 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        {verification?.valid && (
          <span className="flex items-center gap-1.5 text-emerald-400">
            <ShieldCheck className="w-3.5 h-3.5" /> chain verified
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5" /> {c.llm_calls || 0} model calls
        </span>
        <span>{(c.total_tokens || 0).toLocaleString()} tokens</span>
        <span className="flex items-center gap-1.5">
          <Coins className="w-3.5 h-3.5" /> ~${(c.usd || 0).toFixed(4)}
        </span>
      </div>
    </div>
  )
}

function Hero({ onDispatch }) {
  const [input, setInput] = useState('')
  const [listening, setListening] = useState(false)
  const recRef = useRef(null)
  const submit = (e) => {
    e.preventDefault()
    if (input.trim()) onDispatch(input.trim())
  }
  const toggleMic = () => {
    if (listening) {
      recRef.current?.stop()
      return
    }
    const rec = createRecognizer({
      onResult: (text, isFinal) => {
        setInput(text)
        if (isFinal && text.trim()) {
          rec.stop()
          onDispatch(text.trim()) // dictation runs the task hands-free
        }
      },
      onError: () => setListening(false),
      onEnd: () => setListening(false),
    })
    if (!rec) return
    recRef.current = rec
    setListening(true)
    rec.start()
  }
  return (
    <div className="min-h-[58vh] flex flex-col items-center justify-center text-center animate-fade-in">
      <div className="w-12 h-12 rounded-2xl bg-accent/12 border border-accent/25 grid place-items-center mb-6">
        <Sparkles className="w-6 h-6 text-accent" />
      </div>
      <h1 className="text-fg text-3xl font-medium tracking-tight">What should Athena do?</h1>
      <p className="text-muted mt-3 max-w-md">
        Describe a goal. A swarm of agents plans it, does it, and proves every step.
      </p>

      <form onSubmit={submit} className="w-full max-w-2xl mt-8">
        <div className="glass flex items-center gap-2 p-2 pl-4 rounded-2xl">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={listening ? 'Listening…' : 'e.g. summarize how transformers work'}
            className="flex-1 bg-transparent outline-none text-fg placeholder-faint py-2"
            autoFocus
          />
          {recognitionSupported() && (
            <button
              type="button"
              onClick={toggleMic}
              className={`p-2.5 rounded-lg border transition ${
                listening
                  ? 'border-rose-500/50 text-rose-400 bg-rose-500/10 animate-pulse'
                  : 'border-line/16 text-muted hover:text-fg'
              }`}
              aria-label={listening ? 'Stop dictation' : 'Dictate'}
              title={listening ? 'Stop' : 'Speak your task'}
            >
              <Mic className="w-5 h-5" />
            </button>
          )}
          <button type="submit" disabled={!input.trim()} className="btn-accent p-2.5 disabled:opacity-40" aria-label="Run">
            <ArrowUp className="w-5 h-5" />
          </button>
        </div>
      </form>

      <div className="flex flex-wrap justify-center gap-2 mt-5 max-w-2xl">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => onDispatch(ex)}
            className="text-xs px-3 py-1.5 rounded-full border border-line/15 text-muted hover:text-fg hover:border-line/30 transition"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function RunView({ blocks, roleOf, running, result, goal, onDispatch, onReset, verification }) {
  const timeline = useMemo(() => buildTimeline(blocks, roleOf), [blocks, roleOf])
  const hasRun = running || result || blocks.length > 0
  const lastStepIdx = (() => {
    for (let i = timeline.length - 1; i >= 0; i--) if (timeline[i].kind === 'step') return i
    return -1
  })()

  if (!hasRun) return <Hero onDispatch={onDispatch} />

  return (
    <div className="max-w-2xl mx-auto pb-16">
      <div className="flex items-start justify-between gap-4 mb-5">
        <div className="min-w-0">
          <div className="text-faint text-xs uppercase tracking-wide flex items-center gap-2">
            task
            {running && <Loader2 className="w-3 h-3 animate-spin text-accent" />}
          </div>
          <div className="text-fg text-xl leading-snug mt-1">{goal}</div>
        </div>
        <button onClick={onReset} className="btn px-3 py-2 text-sm flex items-center gap-2 shrink-0">
          <Plus className="w-4 h-4" /> New task
        </button>
      </div>

      <div className="space-y-3">
        {timeline.map((item, i) =>
          item.kind === 'plan' ? (
            <PlanCard key={item.index} item={item} />
          ) : item.kind === 'step' ? (
            <StepCard key={item.index} step={item} working={running && i === lastStepIdx && !item.verdict} />
          ) : null,
        )}

        {running && timeline.length === 0 && (
          <div className="card p-4 flex items-center gap-3 animate-fade-in">
            <Loader2 className="w-4 h-4 animate-spin text-accent" />
            <span className="text-muted text-sm">Athena is planning…</span>
          </div>
        )}

        {result && <ResultCard result={result} verification={verification} />}
      </div>
    </div>
  )
}
