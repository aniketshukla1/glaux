import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { ArrowUp, Mic, Square, Paperclip, X, FileText } from 'lucide-react'
import { recognitionSupported, createRecognizer } from '../../lib/speech.js'
import { readFiles, ACCEPT } from './fileExtract.js'
import { BRAND } from '../../lib/brand.js'
import ModelSwitcher from '../ModelSwitcher.jsx'
import PersonaPicker from '../PersonaPicker.jsx'

const SLASH_COMMANDS = [
  { cmd: 'explain', label: 'Explain a concept', desc: 'Break something down clearly', template: 'Explain ' },
  { cmd: 'summarize', label: 'Summarize', desc: 'Condense text or a topic', template: 'Summarize ' },
  { cmd: 'compare', label: 'Compare options', desc: 'Weigh choices and recommend', template: 'Compare ' },
  { cmd: 'plan', label: 'Plan a project', desc: 'Break work into steps', template: 'Plan ' },
  { cmd: 'code', label: 'Write code', desc: 'Generate an implementation', template: 'Write code that ' },
  { cmd: 'research', label: 'Research a topic', desc: 'Investigate in depth', template: 'Research ' },
  { cmd: 'review', label: 'Review and critique', desc: 'Find issues and improvements', template: 'Review and critique ' },
  { cmd: 'debug', label: 'Debug an issue', desc: 'Diagnose and fix', template: 'Debug this: ' },
]

// The message box: text on top, controls underneath. Model and persona live
// here because they apply to the next message. `ref.insert(text)` lets the
// starter cards fill it.
const Composer = forwardRef(function Composer({ onDispatch, running, onStop, recipes = [], hero, model, persona }, ref) {
  const [input, setInput] = useState('')
  const [listening, setListening] = useState(false)
  const [attachments, setAttachments] = useState([])  // { name, content?, error? }
  const [slashIdx, setSlashIdx] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const recRef = useRef(null)
  const taRef = useRef(null)
  const fileRef = useRef(null)

  const slashQuery = /^\/[a-z0-9-]*$/i.test(input) ? input.slice(1).toLowerCase() : null
  const cmdMatches = slashQuery === null ? [] : (() => {
    const byCmd = SLASH_COMMANDS.filter((c) => c.cmd.startsWith(slashQuery))
    return byCmd.length ? byCmd : SLASH_COMMANDS.filter((c) => c.label.toLowerCase().includes(slashQuery))
  })()
  const recipeMatches = slashQuery === null ? []
    : recipes.filter((r) => !slashQuery
        || (r.name || '').toLowerCase().includes(slashQuery)
        || (r.description || '').toLowerCase().includes(slashQuery)).slice(0, 6)
  const slashItems = [
    ...cmdMatches.map((c) => ({ type: 'cmd', command: c })),
    ...recipeMatches.map((r) => ({ type: 'recipe', recipe: r })),
  ]
  const slashOpen = slashItems.length > 0

  const autoGrow = () => {
    const el = taRef.current
    if (el) { el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 240)}px` }
  }
  const setComposerText = (text, selectPlaceholder = false) => {
    setInput(text); setSlashIdx(0)
    requestAnimationFrame(() => {
      autoGrow(); const el = taRef.current; if (!el) return; el.focus()
      const m = selectPlaceholder && text.match(/\{\{\s*[^}]+\s*\}\}/)
      if (m) el.setSelectionRange(m.index, m.index + m[0].length)
      else el.setSelectionRange(text.length, text.length)
    })
  }
  useImperativeHandle(ref, () => ({ insert: (text) => setComposerText(text) }), [])

  const pickItem = (item) => {
    if (!item) return
    if (item.type === 'cmd') setComposerText(item.command.template)
    else setComposerText(item.recipe.prompt || '', true)
  }
  const addFiles = async (files) => {
    const out = await readFiles(files)
    setAttachments((a) => [...a, ...out])
  }
  const send = () => {
    const text = input.trim()
    const good = attachments.filter((a) => a.content)
    if (!text && !good.length) return
    const blob = good.map((a) => `--- ${a.name} ---\n${a.content}`).join('\n\n')
    onDispatch(blob ? `${text}\n\nAttached file(s):\n${blob}`.trim() : text)
    setInput(''); setAttachments([]); requestAnimationFrame(autoGrow)
  }
  const onKeyDown = (e) => {
    if (slashOpen) {
      const n = slashItems.length
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIdx((i) => (i + 1) % n); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSlashIdx((i) => (i - 1 + n) % n); return }
      if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') { e.preventDefault(); pickItem(slashItems[Math.min(slashIdx, n - 1)]); return }
      if (e.key === 'Escape') { e.preventDefault(); setInput(''); return }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
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
    <form onSubmit={(e) => { e.preventDefault(); send() }} className="relative w-full"
      onDragOver={(e) => { if (e.dataTransfer.types?.includes('Files')) { e.preventDefault(); setDragOver(true) } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false) }}
      onDrop={(e) => { if (e.dataTransfer.files?.length) { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) } }}>
      {slashOpen && (
        <div role="listbox" aria-label="Commands and recipes" className="absolute bottom-full mb-2 left-0 right-0 popover p-1 z-20 max-h-80 overflow-y-auto animate-pop-in">
          {cmdMatches.length > 0 && <div className="px-2 pt-1 pb-1 eyebrow">Commands</div>}
          {cmdMatches.map((c, i) => (
            <button type="button" role="option" aria-selected={i === slashIdx} key={`c-${c.cmd}`} onMouseEnter={() => setSlashIdx(i)} onClick={() => pickItem(slashItems[i])}
              className="menu-item" data-active={i === slashIdx}>
              <span className="text-accent mono text-[12.5px] shrink-0">/{c.cmd}</span>
              <span className="text-fg">{c.label}</span>
              <span className="text-faint text-[12px] ml-auto truncate hidden sm:block">{c.desc}</span>
            </button>
          ))}
          {recipeMatches.length > 0 && <div className="px-2 pt-2 pb-1 eyebrow">Recipes</div>}
          {recipeMatches.map((r, j) => {
            const i = cmdMatches.length + j
            return (
              <button type="button" role="option" aria-selected={i === slashIdx} key={`r-${r.id}`} onMouseEnter={() => setSlashIdx(i)} onClick={() => pickItem(slashItems[i])}
                className="menu-item" data-active={i === slashIdx}>
                <span className="shrink-0 w-5 text-center">{r.emoji || '·'}</span>
                <span className="text-fg truncate">{r.name}</span>
                {r.description && <span className="text-faint text-[12px] ml-auto truncate hidden sm:block">{r.description}</span>}
              </button>
            )
          })}
        </div>
      )}

      <div className={`rounded-xl border bg-surface transition-colors shadow-[0_1px_2px_rgb(var(--shadow)/0.12),0_8px_24px_-12px_rgb(var(--shadow)/0.35)] ${
        dragOver ? 'border-accent/60' : 'border-line/[0.14] focus-within:border-line/[0.28]'
      }`}>
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-2.5">
            {attachments.map((a, i) => (
              <span key={i} className={`flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md border text-[12px] ${a.error ? 'border-bad/40 text-bad' : 'border-line/[0.14] text-muted bg-bg/40'}`}>
                <FileText className="w-3.5 h-3.5 shrink-0" />
                <span className="max-w-[180px] truncate">{a.name}</span>
                {a.error && <span className="opacity-80">· {a.error}</span>}
                <button type="button" onClick={() => setAttachments((arr) => arr.filter((_, j) => j !== i))} className="p-0.5 rounded hover:bg-line/10" aria-label={`Remove ${a.name}`}>
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={taRef}
          value={input}
          rows={hero ? 2 : 1}
          onChange={(e) => { setInput(e.target.value); autoGrow() }}
          onKeyDown={onKeyDown}
          aria-label={`Message ${BRAND}`}
          placeholder={listening ? 'Listening…' : dragOver ? 'Drop files to attach' : hero ? `Describe a goal for ${BRAND}…` : 'Reply, or start something new…  ( / for commands )'}
          className="block w-full bg-transparent outline-none focus-visible:outline-none text-fg text-[14px] placeholder:text-faint px-3.5 pt-3 pb-1 resize-none leading-relaxed max-h-[240px]"
          autoFocus={hero}
        />
        <div className="flex items-center gap-0.5 px-2 pb-2 pt-1">
          <input ref={fileRef} type="file" multiple className="hidden" accept={ACCEPT}
            onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          <button type="button" onClick={() => fileRef.current?.click()} className="btn-ghost w-7 h-7"
            aria-label="Attach files" title="Attach text, code, Word or PDF files">
            <Paperclip className="w-4 h-4" />
          </button>
          {model && <ModelSwitcher {...model} />}
          {persona && <PersonaPicker {...persona} />}
          <span className="flex-1" />
          {recognitionSupported() && (
            <button type="button" onClick={toggleMic} aria-pressed={listening}
              className={`w-7 h-7 rounded-md grid place-items-center transition-colors ${listening ? 'text-bad bg-bad/10 animate-pulse' : 'text-muted hover:text-fg hover:bg-line/[0.07]'}`}
              aria-label={listening ? 'Stop dictation' : 'Dictate'} title={listening ? 'Stop' : 'Speak your task'}>
              <Mic className="w-4 h-4" />
            </button>
          )}
          {running ? (
            <button type="button" onClick={onStop} className="ml-1 w-8 h-8 rounded-lg grid place-items-center bg-fg text-bg hover:opacity-90 transition-opacity" aria-label="Stop" title="Stop the running task">
              <Square className="w-3.5 h-3.5" fill="currentColor" />
            </button>
          ) : (
            <button type="submit" disabled={!canSend} className="btn-primary ml-1 w-8 h-8 !rounded-lg" aria-label="Send" title="Send (Enter)">
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </form>
  )
})

export default Composer
