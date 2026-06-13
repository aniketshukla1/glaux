import React from 'react'
import { Hexagon, Sun, Moon, Settings, LayoutGrid, ShieldCheck, Cpu } from 'lucide-react'

export default function TopBar({ theme, onToggleTheme, onOpenStudio, onOpenSettings, verified, health }) {
  const backend = health?.llm || '—'
  const live = health?.live

  return (
    <header className="flex items-center justify-between py-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-accent/15 border border-accent/30 grid place-items-center">
          <Hexagon className="w-5 h-5 text-accent" strokeWidth={2} />
        </div>
        <div className="leading-tight">
          <div className="text-fg font-medium tracking-tight">Athena</div>
          <div className="text-faint text-xs">agent swarm</div>
        </div>
      </div>

      <div className="flex items-center gap-2">
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
