// Turn dropped/attached files into plain text the swarm can read. Text and
// code are read directly; .docx is unzipped natively; PDFs go through pdf.js.
import { extractPdfText } from '../../lib/pdf.js'

const TEXT_EXT = /\.(txt|md|markdown|json|ya?ml|csv|tsv|log|py|js|jsx|ts|tsx|java|c|h|cpp|cc|go|rs|rb|php|sh|bash|zsh|sql|html|css|scss|xml|toml|ini|cfg|conf|env|dockerfile|makefile)$/i
const isTextFile = (f) => (f.type && (f.type.startsWith('text/') || /json|xml|yaml|javascript|csv/.test(f.type))) || TEXT_EXT.test(f.name)
const isDocx = (f) => /\.docx$/i.test(f.name) || f.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const isPdf = (f) => /\.pdf$/i.test(f.name) || f.type === 'application/pdf'
const MAX_FILE = 12 * 1024 * 1024  // 12 MB (PDFs run large)
const MAX_TEXT = 200_000           // cap extracted text fed to the model

export const ACCEPT = '.txt,.md,.markdown,.json,.csv,.tsv,.log,.py,.js,.jsx,.ts,.tsx,.java,.c,.h,.cpp,.go,.rs,.rb,.php,.sh,.sql,.html,.css,.scss,.xml,.yml,.yaml,.toml,.ini,.docx,.pdf,application/pdf,text/*'

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

// Decode XML entities without a DOM round-trip per call.
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

const cap = (s) => (s.length > MAX_TEXT ? `${s.slice(0, MAX_TEXT)}\n…[truncated]` : s)

// Returns one { name, content } or { name, error } per file.
export async function readFiles(files) {
  const out = []
  for (const f of Array.from(files)) {
    if (f.size > MAX_FILE) { out.push({ name: f.name, error: 'too large' }); continue }
    try {
      if (isPdf(f)) {
        const content = await extractPdfText(f)
        out.push(content ? { name: f.name, content: cap(content) } : { name: f.name, error: 'no selectable text (scanned?)' })
      } else if (isDocx(f)) {
        const content = await extractDocxText(f)
        out.push(content ? { name: f.name, content: cap(content) } : { name: f.name, error: 'empty document' })
      } else if (isTextFile(f)) {
        const content = await f.text()
        out.push(looksBinary(content) ? { name: f.name, error: 'binary file' } : { name: f.name, content: cap(content) })
      } else {
        out.push({ name: f.name, error: 'text, code, .docx & .pdf only' })
      }
    } catch { out.push({ name: f.name, error: 'could not read' }) }
  }
  return out
}
