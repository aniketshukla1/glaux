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
