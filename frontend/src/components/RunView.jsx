import React, { useEffect, useRef, useState } from 'react'
import { ArrowDown, GitCompareArrows, Code2, Search, Map as MapIcon, FileText } from 'lucide-react'
import ConstellationSphere from './ConstellationSphere.jsx'
import SwarmField from './SwarmField.jsx'
import Markdown from './Markdown.jsx'
import Trace from './chat/Trace.jsx'
import Answer, { PROSE } from './chat/Answer.jsx'
import Composer from './chat/Composer.jsx'
import { BRAND } from '../lib/brand.js'

const STARTERS = [
  { icon: GitCompareArrows, title: 'Compare options', prompt: 'Compare Postgres and MongoDB for a multi-tenant SaaS and recommend one' },
  { icon: Code2, title: 'Build and test', prompt: 'Write and test a function that finds the median of two sorted arrays in O(log n)' },
  { icon: Search, title: 'Research a topic', prompt: 'Explain how CRISPR-Cas9 edits DNA, then outline the main off-target risks' },
  { icon: MapIcon, title: 'Plan a project', prompt: 'Plan a monolith-to-microservices migration with phases and a rollback strategy' },
]

// Attached files ride inside the directive; show their names, not their bytes.
function splitAttachments(text = '') {
  const m = text.match(/(?:^|\n\n)Attached file\(s\):\n/)
  if (!m) return { body: text, files: [] }
  const rest = text.slice(m.index + m[0].length)
  return { body: text.slice(0, m.index), files: [...rest.matchAll(/^--- (.+) ---$/gm)].map((x) => x[1]) }
}

function UserMessage({ text }) {
  const { body, files } = splitAttachments(text)
  return (
    <div className="flex flex-col items-end gap-1.5">
      {body && (
        <div className="max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 bg-line/[0.08] text-fg text-[14px] leading-relaxed whitespace-pre-wrap break-words">
          {body}
        </div>
      )}
      {files.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5 max-w-[85%]">
          {files.map((f, i) => <span key={i} className="chip"><FileText className="w-3 h-3" />{f}</span>)}
        </div>
      )}
    </div>
  )
}

function Streaming({ text }) {
  // Hide anything from a ```canvas fence onward — the structured canvas renders
  // once the run completes, so raw JSON never flashes while it types.
  const cut = text.indexOf('```canvas')
  return (
    <div className="animate-fade-in" aria-live="polite">
      <Markdown className={PROSE}>{cut >= 0 ? text.slice(0, cut) : text}</Markdown>
      <span className="inline-block w-[3px] h-[1.05em] bg-accent/70 align-text-bottom animate-pulse ml-0.5 rounded-full" />
    </div>
  )
}

// One run as a conversation turn: what you asked, who worked on it, the answer.
function Turn({ directive, blocks, roleOf, running, result, streamingText, verification, onDispatch, createdAt, onOpenProof }) {
  return (
    <article className="space-y-2.5">
      {directive && <UserMessage text={directive} />}
      <Trace blocks={blocks} roleOf={roleOf} running={running} onOpenProof={onOpenProof}
        verified={verification ? verification.valid : null} />
      {running && !result && streamingText && <Streaming text={streamingText} />}
      {result && <Answer result={result} createdAt={createdAt}
        onRegenerate={onDispatch && directive ? () => onDispatch(directive) : undefined} />}
    </article>
  )
}

export default function RunView({
  session, blocks, roleOf, running, result, goal, streamingText, onDispatch, onStop, verification,
  recipes, model, persona, demo, onOpenModel, onOpenProof,
}) {
  const runs = session?.runs || []
  const liveTurn = running || result || (blocks && blocks.length > 0)
  const hasContent = runs.length > 0 || liveTurn
  const composerRef = useRef(null)
  const bottomRef = useRef(null)
  const [atBottom, setAtBottom] = useState(true)
  const composerProps = { onDispatch, running, onStop, recipes, model, persona }

  useEffect(() => {
    const onScroll = () => setAtBottom(window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 160)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [hasContent])
  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [blocks, result, running, streamingText, session?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!hasContent) {
    return (
      <div className="relative flex-1 flex flex-col items-center justify-center px-5 py-10 overflow-hidden">
        <SwarmField className="absolute inset-0 w-full h-full" opacity={0.4} />
        <div className="relative z-10 w-full max-w-3xl flex flex-col items-center text-center animate-fade-in">
          <ConstellationSphere size={196} owlRatio={0.44} />
          <h1 className="text-fg text-[24px] font-semibold tracking-tight mt-1">What should {BRAND} do?</h1>
          <p className="text-muted text-[13.5px] mt-1.5 max-w-md">Describe a goal. A swarm of agents plans it, does it, and signs every step.</p>
          <div className="w-full mt-6 text-left"><Composer ref={composerRef} hero {...composerProps} /></div>
          {demo && (
            <p className="mt-2.5 text-[12px] text-faint">
              Demo mode: answers are simulated. <button onClick={onOpenModel} className="text-accent hover:underline underline-offset-2">Connect a model</button> to get real ones.
            </p>
          )}
          <div className="w-full mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
            {STARTERS.map(({ icon: Icon, title, prompt }) => (
              <button key={title} onClick={() => composerRef.current?.insert(prompt)}
                className="group flex items-start gap-3 p-3 rounded-lg border border-line/[0.1] bg-surface/50 hover:bg-surface hover:border-line/[0.2] transition-colors">
                <Icon className="w-4 h-4 mt-0.5 shrink-0 text-faint group-hover:text-accent transition-colors" />
                <span className="min-w-0">
                  <span className="block text-[13px] text-fg font-medium">{title}</span>
                  <span className="block text-[12px] text-faint mt-0.5 line-clamp-2">{prompt}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="flex-1 w-full max-w-5xl mx-auto px-5 sm:px-8 pt-6 pb-4 space-y-10">
        {runs.map((run) => (
          <Turn key={run.id} directive={run.directive} blocks={run.blocks} roleOf={roleOf} onOpenProof={onOpenProof}
            result={{ success: run.success, final: run.final, cost: run.cost, model: run.model, canvas: run.canvas, sources: run.sources }}
            createdAt={run.created_at} verification={run.verification} onDispatch={onDispatch} />
        ))}
        {liveTurn && (
          <Turn directive={goal} blocks={blocks} roleOf={roleOf} running={running} result={result} onOpenProof={onOpenProof}
            streamingText={streamingText} verification={verification} onDispatch={onDispatch} />
        )}
        <div ref={bottomRef} className="h-px" />
      </div>
      <div className="sticky bottom-0 w-full max-w-5xl mx-auto px-5 sm:px-8 pb-4 pt-3 bg-gradient-to-t from-[rgb(var(--bg))] via-[rgb(var(--bg))] to-transparent">
        {!atBottom && (
          <div className="flex justify-center mb-2.5">
            <button onClick={() => bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })}
              className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-full popover text-muted hover:text-fg animate-fade-in">
              <ArrowDown className="w-3.5 h-3.5" /> Latest
            </button>
          </div>
        )}
        <Composer {...composerProps} />
      </div>
    </div>
  )
}
