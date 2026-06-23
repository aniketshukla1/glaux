// Thin wrappers over the browser Web Speech API — dictation (speech-to-text)
// and read-aloud (text-to-speech). Everything degrades gracefully: callers
// check the *Supported() guards and simply hide the control when absent
// (e.g. SpeechRecognition isn't available in every WebView).

export function recognitionSupported() {
  return typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
}

export function ttsSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

// Create a one-shot recognizer. Returns an object with start()/stop(), or null
// if unsupported. onResult(text, isFinal) fires as the transcript builds.
export function createRecognizer({ onResult, onError, onEnd, lang = 'en-US' } = {}) {
  const SR = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null
  if (!SR) return null
  const rec = new SR()
  rec.lang = lang
  rec.interimResults = true
  rec.continuous = false
  rec.onresult = (e) => {
    let text = ''
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript
    const isFinal = e.results[e.results.length - 1].isFinal
    onResult && onResult(text, isFinal)
  }
  rec.onerror = (e) => onError && onError(e.error || 'error')
  rec.onend = () => onEnd && onEnd()
  return rec
}

// Always-listening wake-word listener. Runs a *continuous* recognizer that scans
// finalized speech for a wake phrase ("Hey Athena …"). If the wake word is
// followed by a command in the same breath, it fires onCommand immediately;
// otherwise it arms and the next utterance becomes the command. Continuous
// recognizers time out on their own, so onend auto-restarts until stop().
const DEFAULT_WAKE = ['hey athena', 'hi athena', 'okay athena', 'ok athena', 'hey athene', 'athena']

export function createWakeListener({ wakeWords = DEFAULT_WAKE, onWake, onCommand, onStatus, onError, lang = 'en-US' } = {}) {
  if (!recognitionSupported()) return null
  let rec = null, running = false, stopped = true, armed = false, restartT = null

  // Detect the wake phrase case-insensitively but return the *original-cased*
  // remainder, so "Hey Athena, compare Redis and Memcached" dispatches with
  // proper nouns intact (not a flattened lowercase string).
  const matchWake = (s) => {
    const text = s || ''
    for (const w of wakeWords) {
      const re = new RegExp('\\b' + w.replace(/\s+/g, '\\s+') + '\\b[\\s,.:;!?-]*', 'i')
      const m = text.match(re)
      if (m) return text.slice(m.index + m[0].length).trim()
    }
    return null  // no wake word present
  }
  const handleFinal = (text) => {
    if (armed) { armed = false; const c = text.trim(); if (c) onCommand && onCommand(c); else onStatus && onStatus('listening'); return }
    const rest = matchWake(text)
    if (rest === null) return
    onWake && onWake()
    if (rest) onCommand && onCommand(rest)
    else { armed = true; onStatus && onStatus('armed') }
  }
  const build = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    rec = new SR(); rec.lang = lang; rec.continuous = true; rec.interimResults = true
    rec.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) handleFinal(e.results[i][0].transcript) }
    rec.onerror = (e) => {
      const err = e.error || 'error'
      if (err === 'not-allowed' || err === 'service-not-allowed') { stopped = true; armed = false; onStatus && onStatus('denied'); onError && onError(err) }
      // no-speech / aborted / network: let onend auto-restart
    }
    rec.onend = () => {
      running = false
      if (!stopped) restartT = setTimeout(() => { try { rec.start(); running = true } catch { /* already running */ } }, 250)
      else onStatus && onStatus('off')
    }
  }
  return {
    start() { stopped = false; armed = false; if (!rec) build(); if (!running) { try { rec.start(); running = true; onStatus && onStatus('listening') } catch { /* already running */ } } },
    stop() { stopped = true; armed = false; clearTimeout(restartT); try { rec && rec.stop() } catch { /* not started */ } },
  }
}

export function speak(text, { onEnd, rate = 1.0 } = {}) {
  if (!ttsSupported() || !text) return false
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = rate
  if (onEnd) u.onend = onEnd
  window.speechSynthesis.speak(u)
  return true
}

export function stopSpeaking() {
  if (ttsSupported()) window.speechSynthesis.cancel()
}
