import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp, Compass, Code2, Search, ShieldCheck, Wrench, Terminal,
  Check, AlertTriangle, ChevronRight, ChevronDown, ArrowDown, Loader2, GraduationCap, BadgeCheck,
  Coins, Cpu, Mic, Volume2, VolumeX, Copy, RotateCcw, Square,
  Globe, FlaskConical, BarChart3, Server, Bug, PenLine, Paperclip, X, FileText,
} from 'lucide-react'
import SwarmGraph from './SwarmGraph.jsx'
import ConstellationSphere from './ConstellationSphere.jsx'
import Canvas from './Canvas.jsx'
import Markdown from './Markdown.jsx'
import { ROLE_META, short, buildTimeline } from '../lib/blocks.js'
import { recognitionSupported, createRecognizer, ttsSupported, speak, stopSpeaking } from '../lib/speech.js'

const ROLE_ICON = {
  router: Compass, coder: Code2, researcher: Search, reflector: ShieldCheck,
  web: Globe, scientist: FlaskConical, analyst: BarChart3, engineer: Server, tester: Bug, writer: PenLine,
  agent: Cpu,
}
const ACT_ICON = { tool: Wrench, skill: Terminal, check: Check, alert: AlertTriangle }

const EXAMPLES = [
  'Explain the mechanism of protein synthesis from transcription to translation, naming the key molecules',
  'Design a rate limiter for a public API: compare token-bucket vs sliding-window and recommend one with pseudocode',
  'Compare PostgreSQL and MongoDB for a multi-tenant SaaS and give a justified recommendation',
  'Implement and stress-test a function that finds the median of two sorted arrays in O(log(m+n))',
  'Explain how CRISPR-Cas9 edits DNA, then outline the main off-target risks',
  'Plan a migration from a monolith to microservices for an e-commerce platform, with phases and a rollback strategy',
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
  const [open, setOpen] = useState(true)
  const meta = ROLE_META[step.role] || ROLE_META.agent
  const status = working ? 'working' : step.verdict === 'retry' ? 'revising' : 'verified'
  return (
    <div className="card p-3.5 animate-fade-up">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-2.5 text-left">
        <Avatar role={step.role} />
        <div className="min-w-0">
          <div className="text-fg text-sm font-medium leading-tight">{meta.label}</div>
          <div className="text-faint text-xs">{meta.sub}</div>
        </div>
        <span className="ml-auto flex items-center gap-2">
          {status === 'working' && <span className="flex items-center gap-1.5 text-xs text-accent"><Loader2 className="w-3.5 h-3.5 animate-spin" /> working</span>}
          {status === 'verified' && <span className="flex items-center gap-1.5 text-xs text-emerald-400"><BadgeCheck className="w-3.5 h-3.5" /> verified</span>}
          {status === 'revising' && <span className="flex items-center gap-1.5 text-xs text-amber-400"><AlertTriangle className="w-3.5 h-3.5" /> revising</span>}
          <ChevronDown className={`w-3.5 h-3.5 text-faint transition ${open ? '' : '-rotate-90'}`} />
        </span>
      </button>
      {open && (
        <>
          {(step.activities.length > 0 || working) && (
            <div className="mt-3 pl-12 space-y-2">
              {step.activities.map((a, i) => {
                const Icon = ACT_ICON[a.icon] || Check
                return (
                  <div key={i} className="flex items-start gap-2.5 text-sm">
                    <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${a.ok ? 'text-muted' : 'text-rose-400'}`} />
                    <div className="min-w-0">
                      <span className="text-fg">{a.text}</span>
                      {a.detail && <span className="text-faint font-mono text-xs ml-2 break-words">{a.detail}</span>}
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
        </>
      )}
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

function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

function ResultCard({ result, verification, onRegenerate, createdAt }) {
  const ok = result.success
  const c = result.cost || {}
  const [speaking, setSpeaking] = useState(false)
  const [copied, setCopied] = useState(false)
  const canSpeak = ttsSupported() && !!result.final
  const toggleSpeak = () => {
    if (speaking) { stopSpeaking(); setSpeaking(false); return }
    if (speak(result.final, { onEnd: () => setSpeaking(false) })) setSpeaking(true)
  }
  const copy = () => { navigator.clipboard?.writeText(result.final || ''); setCopied(true); setTimeout(() => setCopied(false), 1200) }
  return (
    <div className="card p-4 animate-fade-up" style={{ borderColor: ok ? 'rgb(var(--accent) / 0.4)' : undefined }}>
      <div className="flex items-center gap-2 mb-1.5">
        <BadgeCheck className={`w-4 h-4 ${ok ? 'text-accent' : 'text-amber-400'}`} />
        <span className="text-faint text-[11px] uppercase tracking-wide">{ok ? 'Result' : 'Incomplete'}</span>
        <div className="ml-auto flex items-center gap-0.5">
          <button onClick={copy} className="btn p-1" aria-label="Copy answer" title="Copy answer">
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          {onRegenerate && (
            <button onClick={onRegenerate} className="btn p-1" aria-label="Regenerate" title="Ask again">
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}
          {canSpeak && (
            <button onClick={toggleSpeak} className="btn p-1" aria-label={speaking ? 'Stop reading' : 'Read aloud'} title={speaking ? 'Stop reading' : 'Read aloud'}>
              {speaking ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>
      <Markdown className="text-fg text-[13.5px]">{result.final || '—'}</Markdown>
      {result.canvas && <Canvas spec={result.canvas} />}
      {result.budget_halt && <div className="mt-2 text-xs text-amber-400">budget guard: {result.budget_halt}</div>}
      <div className="mt-4 pt-3 border-t border-line/10 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-faint">
        {verification?.valid && <span className="flex items-center gap-1.5 text-emerald-400"><ShieldCheck className="w-3.5 h-3.5" /> chain verified</span>}
        {result.model && <span className="flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> {result.model}</span>}
        <span>{c.llm_calls || 0} calls · {(c.total_tokens || 0).toLocaleString()} tokens</span>
        <span className="flex items-center gap-1.5"><Coins className="w-3.5 h-3.5" /> ~${(c.usd || 0).toFixed(4)}</span>
        <span className="ml-auto">{createdAt ? timeAgo(createdAt) : 'just now'}</span>
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

function StreamingCard({ text }) {
  // Hide anything from a ```canvas fence onward — the structured Canvas renders
  // only once the run completes, so we don't flash raw JSON while typing.
  const cut = text.indexOf('```canvas')
  const shown = cut >= 0 ? text.slice(0, cut) : text
  return (
    <div className="card p-4 animate-fade-in" style={{ borderColor: 'rgb(var(--accent) / 0.3)' }}>
      <div className="flex items-center gap-2 mb-1.5">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
        <span className="text-faint text-[11px] uppercase tracking-wide">Writing the answer…</span>
      </div>
      <Markdown className="text-fg text-[13.5px]">{shown}</Markdown>
      <span className="inline-block w-[3px] h-[1.05em] bg-accent/70 align-text-bottom animate-pulse ml-0.5 rounded-full" />
    </div>
  )
}

// One run rendered as a conversation turn: the directive, the swarm timeline, the result.
function Turn({ directive, blocks, roleOf, running, result, streamingText, verification, onDispatch, createdAt }) {
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
      {running && !result && streamingText && <StreamingCard text={streamingText} />}
      {result && <ResultCard result={result} verification={verification} createdAt={createdAt} onRegenerate={onDispatch && directive ? () => onDispatch(directive) : undefined} />}
    </div>
  )
}

const SLASH_COMMANDS = [
  { cmd: 'explain', label: 'Explain a concept', desc: 'Break something down clearly', template: 'Explain ' },
  { cmd: 'summarize', label: 'Summarize', desc: 'Condense text or a topic', template: 'Summarize ' },
  { cmd: 'compare', label: 'Compare options', desc: 'Weigh choices and recommend', template: 'Compare ' },
  { cmd: 'plan', label: 'Plan a project', desc: 'Break work into steps', template: 'Plan ' },
  { cmd: 'code', label: 'Write code', desc: 'Generate an implementation', template: 'Write code that ' },
  { cmd: 'research', label: 'Research a topic', desc: 'Investigate in depth', template: 'Research ' },
  { cmd: 'review', label: 'Review & critique', desc: 'Find issues and improvements', template: 'Review and critique ' },
  { cmd: 'debug', label: 'Debug an issue', desc: 'Diagnose and fix', template: 'Debug this: ' },
]

const TEXT_EXT = /\.(txt|md|markdown|json|ya?ml|csv|tsv|log|py|js|jsx|ts|tsx|java|c|h|cpp|cc|go|rs|rb|php|sh|bash|zsh|sql|html|css|scss|xml|toml|ini|cfg|conf|env|dockerfile|makefile)$/i
const isTextFile = (f) => (f.type && (f.type.startsWith('text/') || /json|xml|yaml|javascript|csv/.test(f.type))) || TEXT_EXT.test(f.name)
const isDocx = (f) => /\.docx$/i.test(f.name) || f.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const MAX_FILE = 4 * 1024 * 1024  // 4 MB
const MAX_TEXT = 200_000          // cap extracted text fed to the model

// A binary file decoded as UTF-8 is full of U+FFFD / NUL — never feed that to the model.
function looksBinary(s) {
  if (!s) return false
  const n = Math.min(s.length, 4000)
  let bad = 0
  for (let i = 0; i < n; i++) {
    const c = s.charCodeAt(i)
    if (c === 0xfffd || c < 9 || (c > 13 && c < 32) || c === 0x7f) bad++  // replacement + C0 controls + DEL
  }
  return bad / Math.max(n, 1) > 0.02
}

// Decode XML entities + strip tags without a DOM round-trip per call.
function unescapeXml(s) {
  return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(+d)).replace(/&apos;/g, "'").replace(/&amp;/g, '&')
}

// .docx is a ZIP of XML. Pull word/document.xml via the native inflater (no deps) and flatten to text.
async function extractDocxText(file) {
  const buf = await file.arrayBuffer()
  const dv = new DataView(buf)
  const u8 = new Uint8Array(buf)
  let eocd = -1
  for (let i = u8.length - 22; i >= 0 && i > u8.length - 22 - 65536; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break }
  }
  if (eocd < 0) throw new Error('not a docx')
  const entries = dv.getUint16(eocd + 10, true)
  let p = dv.getUint32(eocd + 16, true)
  const dec = new TextDecoder()
  for (let e = 0; e < entries; e++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break
    const method = dv.getUint16(p + 10, true)
    const compSize = dv.getUint32(p + 20, true)
    const nameLen = dv.getUint16(p + 28, true)
    const extraLen = dv.getUint16(p + 30, true)
    const commentLen = dv.getUint16(p + 32, true)
    const localOff = dv.getUint32(p + 42, true)
    const name = dec.decode(u8.subarray(p + 46, p + 46 + nameLen))
    if (name === 'word/document.xml') {
      const lNameLen = dv.getUint16(localOff + 26, true)
      const lExtraLen = dv.getUint16(localOff + 28, true)
      const start = localOff + 30 + lNameLen + lExtraLen
      const comp = u8.subarray(start, start + compSize)
      let bytes = comp
      if (method === 8) {
        const ds = new DecompressionStream('deflate-raw')
        const stream = new Response(comp).body.pipeThrough(ds)
        bytes = new Uint8Array(await new Response(stream).arrayBuffer())
      }
      const xml = new TextDecoder().decode(bytes)
      const text = xml
        .replace(/<w:tab\b[^>]*\/?>/g, '\t')
        .replace(/<\/w:p>/g, '\n')
        .replace(/<[^>]+>/g, '')
      return unescapeXml(text).replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
    }
    p += 46 + nameLen + extraLen + commentLen
  }
  throw new Error('no document body')
}

function Composer({ onDispatch, hero, running, onStop }) {
  const [input, setInput] = useState('')
  const [listening, setListening] = useState(false)
  const [attachments, setAttachments] = useState([])  // { name, content?, error? }
  const [slashIdx, setSlashIdx] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const recRef = useRef(null)
  const taRef = useRef(null)
  const fileRef = useRef(null)

  const slashQuery = /^\/[a-z0-9-]*$/i.test(input) ? input.slice(1).toLowerCase() : null
  const byCmd = slashQuery === null ? [] : SLASH_COMMANDS.filter((c) => c.cmd.startsWith(slashQuery))
  const slashMatches = slashQuery === null ? []
    : byCmd.length ? byCmd : SLASH_COMMANDS.filter((c) => c.label.toLowerCase().includes(slashQuery))
  const slashOpen = slashMatches.length > 0

  const autoGrow = () => {
    const el = taRef.current
    if (el) { el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 200)}px` }
  }
  const pickSlash = (c) => {
    setInput(c.template); setSlashIdx(0)
    requestAnimationFrame(() => { autoGrow(); const el = taRef.current; if (el) { el.focus(); el.setSelectionRange(c.template.length, c.template.length) } })
  }
  const addFiles = async (files) => {
    const out = []
    for (const f of Array.from(files)) {
      if (f.size > MAX_FILE) { out.push({ name: f.name, error: 'too large' }); continue }
      try {
        if (isDocx(f)) {
          let content = await extractDocxText(f)
          if (!content) { out.push({ name: f.name, error: 'empty document' }); continue }
          if (content.length > MAX_TEXT) content = content.slice(0, MAX_TEXT) + '\n…[truncated]'
          out.push({ name: f.name, content })
        } else if (isTextFile(f)) {
          let content = await f.text()
          if (looksBinary(content)) { out.push({ name: f.name, error: 'binary file' }); continue }
          if (content.length > MAX_TEXT) content = content.slice(0, MAX_TEXT) + '\n…[truncated]'
          out.push({ name: f.name, content })
        } else {
          out.push({ name: f.name, error: 'text, code & .docx only' })
        }
      } catch { out.push({ name: f.name, error: 'could not read' }) }
    }
    setAttachments((a) => [...a, ...out])
  }
  const send = () => {
    const text = input.trim()
    const good = attachments.filter((a) => a.content)
    if (!text && !good.length) return
    const blob = good.map((a) => `--- ${a.name} ---\n${a.content}`).join('\n\n')
    const directive = blob ? `${text}\n\nAttached file(s):\n${blob}`.trim() : text
    onDispatch(directive)
    setInput(''); setAttachments([]); requestAnimationFrame(autoGrow)
  }
  const submit = (e) => { e.preventDefault(); send() }
  const onKeyDown = (e) => {
    if (slashOpen) {
      const pick = () => pickSlash(slashMatches[Math.min(slashIdx, slashMatches.length - 1)])
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIdx((i) => (i + 1) % slashMatches.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSlashIdx((i) => (i - 1 + slashMatches.length) % slashMatches.length); return }
      if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') { e.preventDefault(); pick(); return }
      if (e.key === 'Escape') { e.preventDefault(); setInput(''); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }
  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return }
    const rec = createRecognizer({
      onResult: (text, isFinal) => { setInput(text); requestAnimationFrame(autoGrow); if (isFinal && text.trim()) { rec.stop(); onDispatch(text.trim()); setInput('') } },
      onError: () => setListening(false),
      onEnd: () => setListening(false),
    })
    if (!rec) return
    recRef.current = rec; setListening(true); rec.start()
  }
  const canSend = !!input.trim() || attachments.some((a) => a.content)
  return (
    <form onSubmit={submit} className={`relative ${hero ? 'w-full max-w-2xl mt-7' : 'w-full'}`}
      onDragOver={(e) => { if (e.dataTransfer.types?.includes('Files')) { e.preventDefault(); setDragOver(true) } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false) }}
      onDrop={(e) => { if (e.dataTransfer.files?.length) { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) } }}>
      {slashOpen && (
        <div className="absolute bottom-full mb-2 left-0 right-0 card p-1.5 shadow-2xl z-20 max-h-72 overflow-y-auto">
          <div className="px-2 py-1 text-xs text-faint">Commands · ↑↓ to move, ↵ to insert</div>
          {slashMatches.map((c, i) => (
            <button type="button" key={c.cmd} onMouseEnter={() => setSlashIdx(i)} onClick={() => pickSlash(c)}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition ${i === slashIdx ? 'bg-line/10' : 'hover:bg-line/5'}`}>
              <span className="text-accent text-sm font-mono shrink-0">/{c.cmd}</span>
              <span className="text-fg text-sm">{c.label}</span>
              <span className="text-faint text-xs ml-auto truncate hidden sm:block">{c.desc}</span>
            </button>
          ))}
        </div>
      )}
      <div className={`glass rounded-xl p-1.5 transition ${dragOver ? 'ring-2 ring-accent/60' : ''}`}>
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1.5 pt-1 pb-2">
            {attachments.map((a, i) => (
              <span key={i} className={`flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-lg border text-xs ${a.error ? 'border-rose-500/40 text-rose-400' : 'border-line/16 text-muted'}`}>
                <FileText className="w-3.5 h-3.5 shrink-0" />
                <span className="max-w-[160px] truncate">{a.name}</span>
                {a.error && <span className="opacity-70">· {a.error}</span>}
                <button type="button" onClick={() => setAttachments((arr) => arr.filter((_, j) => j !== i))} className="p-0.5 rounded hover:bg-line/10" aria-label="Remove attachment">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-1.5 pl-2">
          <textarea
            ref={taRef}
            value={input}
            rows={1}
            onChange={(e) => { setInput(e.target.value); autoGrow() }}
            onKeyDown={onKeyDown}
            placeholder={listening ? 'Listening…' : dragOver ? 'Drop files to attach…' : hero ? 'e.g. summarize how transformers work   ·   type / for commands' : 'Ask Athena…  (/ for commands, Shift+Enter for a new line)'}
            className="flex-1 bg-transparent outline-none text-fg text-sm placeholder-faint py-1.5 resize-none leading-relaxed max-h-[200px]"
            autoFocus={hero}
          />
          <input ref={fileRef} type="file" multiple className="hidden"
            accept=".txt,.md,.markdown,.json,.csv,.tsv,.log,.py,.js,.jsx,.ts,.tsx,.java,.c,.h,.cpp,.go,.rs,.rb,.php,.sh,.sql,.html,.css,.scss,.xml,.yml,.yaml,.toml,.ini,.docx,text/*"
            onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          <button type="button" onClick={() => fileRef.current?.click()}
            className="p-2 rounded-lg border border-line/16 text-muted hover:text-fg transition shrink-0"
            aria-label="Attach files" title="Attach text, code or Word (.docx) files">
            <Paperclip className="w-4 h-4" />
          </button>
          {recognitionSupported() && (
            <button type="button" onClick={toggleMic}
              className={`p-2 rounded-lg border transition shrink-0 ${listening ? 'border-rose-500/50 text-rose-400 bg-rose-500/10 animate-pulse' : 'border-line/16 text-muted hover:text-fg'}`}
              aria-label={listening ? 'Stop dictation' : 'Dictate'} title={listening ? 'Stop' : 'Speak your task'}>
              <Mic className="w-4 h-4" />
            </button>
          )}
          {running ? (
            <button type="button" onClick={onStop} className="p-2 rounded-lg border border-rose-500/50 text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 transition shrink-0" aria-label="Stop" title="Stop the running task">
              <Square className="w-4 h-4" fill="currentColor" />
            </button>
          ) : (
            <button type="submit" disabled={!canSend} className="btn-accent p-2 disabled:opacity-40 shrink-0" aria-label="Run">
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </form>
  )
}

export default function RunView({ session, blocks, roleOf, running, result, goal, streamingText, onDispatch, onStop, verification }) {
  const runs = session?.runs || []
  const liveTurn = running || result || (blocks && blocks.length > 0)
  const hasContent = runs.length > 0 || liveTurn

  const bottomRef = useRef(null)
  const [atBottom, setAtBottom] = useState(true)
  useEffect(() => {
    const onScroll = () => {
      setAtBottom(window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 160)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [hasContent])
  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [blocks, result, running, session?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!hasContent) {
    return (
      <div className="min-h-[72vh] flex flex-col items-center justify-center text-center animate-fade-in px-5">
        <ConstellationSphere size={300} />
        <h1 className="text-fg text-2xl font-medium tracking-tight -mt-4">What should Athena do?</h1>
        <p className="text-muted text-sm mt-2.5 max-w-md">Describe a goal. A swarm of agents plans it, does it, and proves every step.</p>
        <Composer onDispatch={onDispatch} hero running={running} onStop={onStop} />
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
            result={{ success: run.success, final: run.final, cost: run.cost, model: run.model, canvas: run.canvas }}
            createdAt={run.created_at} verification={run.verification} onDispatch={onDispatch} />
        ))}
        {liveTurn && (
          <Turn directive={goal} blocks={blocks} roleOf={roleOf} running={running} result={result} streamingText={streamingText} verification={verification} onDispatch={onDispatch} />
        )}
        <div ref={bottomRef} className="h-px" />
      </div>
      <div className="sticky bottom-0 w-full max-w-5xl mx-auto px-5 sm:px-8 pb-5 pt-3 bg-gradient-to-t from-[rgb(var(--bg))] via-[rgb(var(--bg))] to-transparent">
        {!atBottom && (
          <div className="flex justify-center mb-2.5">
            <button
              onClick={() => bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full glass text-muted hover:text-fg shadow-lg animate-fade-in"
            >
              <ArrowDown className="w-3.5 h-3.5" /> Latest
            </button>
          </div>
        )}
        <Composer onDispatch={onDispatch} running={running} onStop={onStop} />
      </div>
    </div>
  )
}
