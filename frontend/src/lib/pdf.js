// PDF → plain text, extracted in the browser with pdf.js. Everything here is
// dynamically imported so the (large) PDF engine only downloads the first time
// someone actually attaches a PDF — it never touches the initial bundle.

let _pdfjs = null

async function loadPdfjs() {
  if (_pdfjs) return _pdfjs
  const pdfjs = await import('pdfjs-dist')
  // Vite resolves the worker to a hashed asset URL via the ?url suffix.
  const workerUrl = (await import('pdfjs-dist/build/pdf.worker.min.mjs?url')).default
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl
  _pdfjs = pdfjs
  return pdfjs
}

// Returns the document's selectable text. Empty string means there was none to
// extract (e.g. a scanned/image-only PDF) — the caller decides how to message that.
export async function extractPdfText(file, { maxPages = 50, maxChars = 200_000 } = {}) {
  const pdfjs = await loadPdfjs()
  const data = new Uint8Array(await file.arrayBuffer())
  const doc = await pdfjs.getDocument({ data, isEvalSupported: false, disableFontFace: true }).promise
  try {
    const pages = Math.min(doc.numPages, maxPages)
    const out = []
    let total = 0
    for (let p = 1; p <= pages; p++) {
      const page = await doc.getPage(p)
      const content = await page.getTextContent()
      const parts = []
      for (const it of content.items) {
        if (typeof it.str !== 'string') continue
        parts.push(it.str)
        parts.push(it.hasEOL ? '\n' : ' ')
      }
      const text = parts.join('').replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n')
      out.push(text)
      total += text.length
      if (total > maxChars) break
    }
    return out.join('\n\n').replace(/\n{3,}/g, '\n\n').trim()
  } finally {
    try { await doc.destroy() } catch { /* ignore */ }
  }
}
