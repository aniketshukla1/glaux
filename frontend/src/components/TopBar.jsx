import React from 'react'
import { Sun, Moon, Settings, LayoutGrid, ShieldCheck, Cpu, Search } from 'lucide-react'

export default function TopBar({ title, theme, onToggleTheme, onOpenStudio, onOpenSettings, onOpenPalette, verified, health }) {
  const backend = health?.llm || '—'
  const live = health?.live

  return (
    <header className="flex items-center justify-between py-4 gap-3">
      <div className="min-w-0 text-fg font-medium tracking-tight truncate">{title || 'Athena'}</div>

      <div className="flex items-center gap-2 shrink-0">
        {verified != null && (
          <span
            className={`hidden sm:flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border ${
              verified
                ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                : 'text-rose-400 border-rose-500/30 bg-rose-500/10'
            }`}
            title="Every action is cryptographically signed and the chain is verified"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            {verified ? 'verified' : 'tampered'}
          </span>
        )}
        <span
          className="hidden md:flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-line/15 text-muted"
          title="Active model"
        >
          <Cpu className="w-3.5 h-3.5" style={{ color: live ? 'rgb(var(--accent))' : undefined }} />
          {backend}
        </span>
        <button onClick={onOpenPalette} className="btn px-2.5 py-2 hidden sm:flex items-center gap-1.5" aria-label="Command palette" title="Command palette (⌘K)">
          <Search className="w-4 h-4" />
          <kbd className="text-[10px] text-faint">⌘K</kbd>
        </button>
        <button onClick={onToggleTheme} className="btn p-2" aria-label="Toggle theme">
          {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
        </button>
        <button onClick={onOpenStudio} className="btn px-3 py-2 flex items-center gap-2 text-sm">
          <LayoutGrid className="w-4 h-4" />
          <span className="hidden sm:inline">Studio</span>
        </button>
        <button onClick={onOpenSettings} className="btn p-2" aria-label="Settings">
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  )
}
