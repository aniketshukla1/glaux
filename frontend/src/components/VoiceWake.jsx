import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic, X, Volume2, VolumeX, Loader2 } from 'lucide-react'
import { createWakeListener, recognitionSupported, ttsSupported, speak, stopSpeaking } from '../lib/speech.js'
import { BRAND } from '../lib/brand.js'

// Hands-free mode. Lives at the app root so it survives view changes. While
// enabled it continuously listens for "Hey Glaux …" and dispatches whatever
// follows. It goes quiet while a task runs (and while reading a reply aloud) so
// it never hears itself, then resumes. A floating pill makes the state obvious —
// always-listening should never be invisible.
export default function VoiceWake({ enabled, running, result, onDispatch, onDisable }) {
  const [status, setStatus] = useState('off')     // off | listening | armed | denied
  const [speaking, setSpeaking] = useState(false)
  const [speakReplies, setSpeakReplies] = useState(() => localStorage.getItem('athena-wake-tts') === '1')
  const listenerRef = useRef(null)
  const dispatchRef = useRef(onDispatch)
  const disableRef = useRef(onDisable)
  const lastSpokenRef = useRef(null)
  useEffect(() => { dispatchRef.current = onDispatch; disableRef.current = onDisable })

  // Build the listener once; always reach the latest callbacks via refs.
  useEffect(() => {
    if (!recognitionSupported()) return undefined
    const l = createWakeListener({
      onCommand: (cmd) => dispatchRef.current && dispatchRef.current(cmd),
      onStatus: (s) => setStatus(s),
      onError: () => { disableRef.current && disableRef.current() },  // mic blocked → flip the toggle off
    })
    listenerRef.current = l
    return () => { l && l.stop() }
  }, [])

  // Listen only when enabled and nothing is talking back (task running / TTS).
  const shouldListen = enabled && !running && !speaking && recognitionSupported()
  useEffect(() => {
    const l = listenerRef.current
    if (!l) return
    if (shouldListen) l.start()
    else { l.stop(); if (!enabled) { setStatus('off'); stopSpeaking() } }
  }, [shouldListen, enabled])

  // Read the answer aloud (optional). Stays quiet again until it finishes.
  useEffect(() => {
    if (!enabled || !speakReplies || !result) return
    const text = result.final || result.synthesized || ''
    if (!text || lastSpokenRef.current === text) return
    lastSpokenRef.current = text
    setSpeaking(true)
    const ok = speak(text.slice(0, 700), { onEnd: () => setSpeaking(false) })
    if (!ok) setSpeaking(false)
  }, [result, enabled, speakReplies])

  useEffect(() => { localStorage.setItem('athena-wake-tts', speakReplies ? '1' : '0') }, [speakReplies])

  if (!enabled || !recognitionSupported()) return null

  const denied = status === 'denied'
  const label = denied ? 'Microphone blocked — allow access'
    : running ? 'Working on it…'
    : speaking ? 'Speaking…'
    : status === 'armed' ? 'Listening… say your task'
    : `Listening for “Hey ${BRAND}”`
  const busy = running || speaking
  const armed = status === 'armed'

  return createPortal(
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2.5 pl-3 pr-2 py-2 rounded-full glass shadow-2xl border border-line/15">
      <span className="relative flex items-center justify-center w-6 h-6">
        {!busy && !denied && (
          <span className={`absolute inline-flex w-full h-full rounded-full ${armed ? 'bg-accent/40' : 'bg-ok/40'} animate-ping`} />
        )}
        {busy
          ? <Loader2 className="w-4 h-4 text-accent animate-spin" />
          : <Mic className={`w-4 h-4 ${denied ? 'text-bad' : armed ? 'text-accent' : 'text-ok'}`} />}
      </span>
      <span className="text-fg text-[13px] whitespace-nowrap pr-0.5">{label}</span>
      {ttsSupported() && (
        <button onClick={() => setSpeakReplies((v) => !v)}
          className={`p-1.5 rounded-full transition ${speakReplies ? 'text-accent bg-accent/10' : 'text-faint hover:text-fg'}`}
          aria-label={speakReplies ? 'Mute spoken replies' : 'Speak replies aloud'}
          title={speakReplies ? 'Spoken replies on' : 'Speak replies aloud'}>
          {speakReplies ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
        </button>
      )}
      <button onClick={() => onDisable && onDisable()} className="p-1.5 rounded-full text-faint hover:text-fg hover:bg-line/10 transition" aria-label="Turn off hands-free" title="Turn off hands-free">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>,
    document.body,
  )
}
