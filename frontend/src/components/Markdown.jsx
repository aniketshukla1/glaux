import React, { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github-dark.css'
import { Copy, Check } from 'lucide-react'

const toText = (c) => (Array.isArray(c) ? c.map(toText).join('') : c == null ? '' : String(c))
const escapeHtml = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))

function CodeBlock({ lang, text }) {
  const [copied, setCopied] = useState(false)
  const html = useMemo(() => {
    try {
      if (lang && hljs.getLanguage(lang)) return hljs.highlight(text, { language: lang }).value
      return hljs.highlightAuto(text).value
    } catch {
      return escapeHtml(text)
    }
  }, [text, lang])
  const copy = () => {
    navigator.clipboard?.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }
  return (
    <div className="my-2 rounded-lg overflow-hidden border border-line/15 text-left">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0d1117] text-faint text-[11px] border-b border-white/5">
        <span className="uppercase tracking-wide">{lang || 'code'}</span>
        <button onClick={copy} className="flex items-center gap-1 hover:text-fg transition">
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />} {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <pre className="hljs !bg-[#0d1117] text-[12.5px] leading-relaxed p-3 overflow-x-auto m-0">
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  )
}

const components = {
  // block code: <pre> wraps a <code>; we don't render the default child so the
  // inline `code` override below only ever sees inline code.
  pre({ children }) {
    const codeEl = Array.isArray(children) ? children[0] : children
    const cls = codeEl?.props?.className || ''
    const match = /language-(\w+)/.exec(cls)
    const text = toText(codeEl?.props?.children).replace(/\n$/, '')
    return <CodeBlock lang={match ? match[1] : ''} text={text} />
  },
  code: ({ children, ...props }) => (
    <code className="px-1 py-0.5 rounded bg-line/15 text-[0.86em] font-mono break-words" {...props}>{children}</code>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2 hover:opacity-80">{children}</a>
  ),
  p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-1.5 pl-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 pl-5 list-decimal space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <h1 className="text-fg font-semibold text-base mt-3 mb-1.5">{children}</h1>,
  h2: ({ children }) => <h2 className="text-fg font-semibold text-[15px] mt-3 mb-1.5">{children}</h2>,
  h3: ({ children }) => <h3 className="text-fg font-medium text-[14px] mt-2.5 mb-1">{children}</h3>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-accent/40 pl-3 my-2 text-muted">{children}</blockquote>,
  hr: () => <hr className="my-3 border-line/15" />,
  strong: ({ children }) => <strong className="font-semibold text-fg">{children}</strong>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto"><table className="w-full text-[12.5px] border-collapse">{children}</table></div>
  ),
  th: ({ children }) => <th className="border border-line/15 px-2 py-1 text-left bg-line/8 font-medium">{children}</th>,
  td: ({ children }) => <td className="border border-line/15 px-2 py-1 align-top">{children}</td>,
  img: ({ src, alt }) => <img src={src} alt={alt} className="my-2 rounded-lg max-w-full border border-line/15" />,
}

export default function Markdown({ children, className = '' }) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children || ''}
      </ReactMarkdown>
    </div>
  )
}
