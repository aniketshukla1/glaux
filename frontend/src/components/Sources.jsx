import React from 'react'
import { Link2, ExternalLink } from 'lucide-react'

// Citations for a run — the pages the swarm actually browsed (web_fetch /
// web_search), never fabricated. Letter badges instead of remote favicons so we
// don't leak the visited domains to a third-party favicon service.
const domainOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return String(url || '') } }

const BADGE = ['#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#22d3ee', '#f59e0b']
const colorFor = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return BADGE[h % BADGE.length] }

export default function Sources({ sources }) {
  if (!sources || !sources.length) return null
  return (
    <div className="mt-4 pt-3 border-t border-line/10">
      <div className="flex items-center gap-1.5 text-faint text-[11px] uppercase tracking-wide mb-2">
        <Link2 className="w-3.5 h-3.5" /> Sources · {sources.length}
      </div>
      <div className="grid sm:grid-cols-2 gap-1.5">
        {sources.map((s, i) => {
          const domain = domainOf(s.url)
          return (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
              title={s.url}
              className="group flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-line/12 hover:border-line/25 hover:bg-line/5 transition min-w-0">
              <span className="text-faint text-[11px] w-3.5 shrink-0 text-right tabular-nums">{i + 1}</span>
              <span className="w-5 h-5 rounded shrink-0 flex items-center justify-center text-[10px] font-semibold text-white"
                style={{ background: colorFor(domain) }}>{(domain[0] || '?').toUpperCase()}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-fg text-xs truncate">{s.title || domain}</span>
                <span className="block text-faint text-[10px] truncate">{domain}</span>
              </span>
              <ExternalLink className="w-3 h-3 text-faint opacity-0 group-hover:opacity-100 transition shrink-0" />
            </a>
          )
        })}
      </div>
    </div>
  )
}
