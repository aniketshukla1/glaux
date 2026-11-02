// Export a conversation to Markdown — title, each turn (you → Glaux), and the
import { BRAND } from './brand.js'
// verified-chain / cost metadata. Pure client-side from the loaded session.

function runToMarkdown(run) {
  const out = [`## You\n\n${run.directive || ''}`, `\n## ${BRAND}\n\n${run.final || '—'}`]
  const c = run.cost || {}
  const bits = []
  if (run.verification?.valid) bits.push('chain verified')
  if (run.model) bits.push(run.model)
  if (c.llm_calls != null) bits.push(`${c.llm_calls} calls`)
  if (c.total_tokens) bits.push(`${c.total_tokens.toLocaleString()} tokens`)
  if (c.usd) bits.push(`$${Number(c.usd).toFixed(4)}`)
  if (bits.length) out.push(`\n*${bits.join(' · ')}*`)
  if (run.sources?.length) {
    out.push('\n**Sources**')
    run.sources.forEach((s, i) => out.push(`${i + 1}. [${s.title || s.url}](${s.url})`))
  }
  return out.join('\n')
}

export function conversationToMarkdown(session) {
  const runs = session?.runs || []
  const header = `# ${session?.title || 'Conversation'}\n\n> Exported from ${BRAND} · ${new Date().toLocaleString()}\n`
  if (!runs.length) return `${header}\n_(no messages yet)_\n`
  return `${header}\n${runs.map(runToMarkdown).join('\n\n---\n\n')}\n`
}

export function download(filename, text, type = 'text/markdown') {
  try {
    const blob = new Blob([text], { type })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { /* non-browser */ }
}

const slug = (s) => (s || 'conversation').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || 'conversation'

export function exportConversation(session) {
  download(`${slug(session?.title)}.md`, conversationToMarkdown(session))
}
