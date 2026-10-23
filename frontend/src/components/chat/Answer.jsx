import React, { useState } from 'react'
import { Copy, Check, RotateCcw, Volume2, VolumeX, Zap, AlertTriangle } from 'lucide-react'
import Markdown from '../Markdown.jsx'
import Canvas from '../Canvas.jsx'
import Sources from '../Sources.jsx'
import { ttsSupported, speak, stopSpeaking } from '../../lib/speech.js'

function timeAgo(iso) {
  if (!iso) return 'just now'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

export const PROSE = 'text-fg text-[14px] leading-[1.65]'

// The swarm's answer as plain prose — the answer leads, not the chrome around
// it. Actions and run facts sit quietly underneath.
export default function Answer({ result, createdAt, onRegenerate }) {
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
  const facts = [
    result.cached ? null : result.model,
    `${(c.total_tokens || 0).toLocaleString()} tokens`,
    `$${(c.usd || 0).toFixed(4)}`,
  ].filter(Boolean)

  return (
    <div className="group/answer animate-fade-in">
      {!ok && (
        <div className="mb-2 flex items-center gap-1.5 text-[12.5px] text-warn">
          <AlertTriangle className="w-3.5 h-3.5" /> The swarm couldn’t fully finish this one.
        </div>
      )}
      <Markdown className={PROSE}>{result.final || '—'}</Markdown>
      {result.canvas && <Canvas spec={result.canvas} />}
      <Sources sources={result.sources} />
      {result.budget_halt && <div className="mt-2 text-[12px] text-warn">Stopped by the budget guard: {result.budget_halt}</div>}

      <div className="mt-2 flex flex-wrap items-center gap-y-1 text-[11.5px] text-faint">
        <button onClick={copy} className="btn-ghost w-7 h-7" aria-label="Copy answer" title="Copy">
          {copied ? <Check className="w-3.5 h-3.5 text-ok" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
        {onRegenerate && (
          <button onClick={onRegenerate} className="btn-ghost w-7 h-7" aria-label="Run again" title="Run again">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        )}
        {canSpeak && (
          <button onClick={toggleSpeak} className="btn-ghost w-7 h-7" aria-label={speaking ? 'Stop reading' : 'Read aloud'} title={speaking ? 'Stop reading' : 'Read aloud'}>
            {speaking ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
          </button>
        )}
        <span className="ml-2 flex flex-wrap items-center gap-x-1.5">
          {result.cached && (
            <span className="flex items-center gap-1 text-warn" title={result.matched_directive ? `Matched an earlier ask: “${result.matched_directive}”` : 'Served from the answer cache'}>
              <Zap className="w-3 h-3" /> from cache ·
            </span>
          )}
          {facts.map((f, i) => <span key={i}>{i > 0 && <span className="mr-1.5">·</span>}{f}</span>)}
          <span className="mr-1.5">·</span><span>{timeAgo(createdAt)}</span>
        </span>
      </div>
    </div>
  )
}
