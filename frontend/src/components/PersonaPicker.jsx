import React from 'react'
import { ChevronDown, Sparkles, SlidersHorizontal } from 'lucide-react'
import { Menu, MenuItem, MenuLabel, MenuSeparator } from './ui/Menu.jsx'

// The active chat's persona, as a composer chip. Hidden until at least one
// persona exists — an empty picker is clutter.
export default function PersonaPicker({ personas = [], activeId, onPick, onManage }) {
  if (!personas.length) return null
  const active = personas.find((p) => p.id === activeId)
  return (
    <Menu side="top" align="start" width="w-56"
      trigger={(t) => (
        <button {...t} type="button" title="Persona for this chat"
          className="flex items-center gap-1.5 h-7 px-2 rounded-md text-[12px] text-muted hover:text-fg hover:bg-line/[0.07] transition-colors">
          {active?.emoji ? <span className="leading-none">{active.emoji}</span> : <Sparkles className="w-3.5 h-3.5" />}
          <span className="max-w-[120px] truncate">{active ? active.name : 'Persona'}</span>
          <ChevronDown className="w-3 h-3 opacity-70 shrink-0" />
        </button>
      )}>
      <MenuLabel>Persona</MenuLabel>
      <MenuItem checked={!activeId} onSelect={() => onPick(null)}>None</MenuItem>
      {personas.map((p) => (
        <MenuItem key={p.id} checked={p.id === activeId} onSelect={() => onPick(p.id)}>
          {p.emoji ? `${p.emoji}  ` : ''}{p.name}
        </MenuItem>
      ))}
      <MenuSeparator />
      <MenuItem icon={SlidersHorizontal} onSelect={onManage}>Manage personas…</MenuItem>
    </Menu>
  )
}
