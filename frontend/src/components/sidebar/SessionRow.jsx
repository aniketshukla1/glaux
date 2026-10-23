import React, { useEffect, useRef, useState } from 'react'
import { MoreHorizontal, Pin, PinOff, Pencil, FolderInput, Trash2, Folder } from 'lucide-react'
import { Menu, MenuItem, MenuLabel, MenuSeparator } from '../ui/Menu.jsx'

// One conversation in the sidebar. The title is a real <button> so the list is
// keyboard-navigable; actions live in a single overflow menu rather than a row
// of hover-only icons.
export default function SessionRow({ s, active, projects, onSelect, onRename, onDelete, onMove, onPin }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(s.title)
  const inputRef = useRef(null)

  const commit = () => {
    setEditing(false)
    const t = val.trim()
    if (t && t !== s.title) onRename(s.id, t)
  }
  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])

  const moveTargets = [
    ...(s.project_id ? [{ id: null, name: 'No project' }] : []),
    ...projects.filter((p) => p.id !== s.project_id),
  ]

  return (
    <div
      draggable={!editing}
      onDragStart={(e) => { e.dataTransfer.setData('text/athena-session', s.id); e.dataTransfer.effectAllowed = 'move' }}
      className={`group relative flex items-center rounded-md transition-colors ${
        active ? 'bg-line/[0.09] text-fg' : 'text-muted hover:text-fg hover:bg-line/[0.05]'
      }`}
    >
      {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-accent" aria-hidden="true" />}
      {editing ? (
        <input
          ref={inputRef}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setVal(s.title); setEditing(false) } }}
          onBlur={commit}
          aria-label="Conversation title"
          className="flex-1 min-w-0 mx-1.5 my-1 px-1.5 py-0.5 bg-bg rounded border border-accent/50 outline-none text-[13px] text-fg"
        />
      ) : (
        <button
          onClick={() => onSelect(s.id)}
          aria-current={active ? 'page' : undefined}
          className="flex-1 min-w-0 flex items-center gap-1.5 pl-2.5 pr-1 py-[5px] text-left text-[13px]"
        >
          {s.pinned && <Pin className="w-3 h-3 shrink-0 text-faint fill-current" aria-label="Pinned" />}
          <span className="truncate">{s.title}</span>
        </button>
      )}
      {!editing && (
        <Menu
          align="end"
          width="w-52"
          className="shrink-0"
          trigger={(t) => (
            <button {...t} aria-label={`Actions for ${s.title}`}
              className={`mr-1 p-1 rounded text-faint hover:text-fg hover:bg-line/10 transition-opacity ${
                t.open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'
              }`}>
              <MoreHorizontal className="w-3.5 h-3.5" />
            </button>
          )}
        >
          <MenuItem icon={s.pinned ? PinOff : Pin} onSelect={() => onPin(s.id, !s.pinned)}>{s.pinned ? 'Unpin' : 'Pin to top'}</MenuItem>
          <MenuItem icon={Pencil} onSelect={() => { setVal(s.title); setEditing(true) }}>Rename</MenuItem>
          {moveTargets.length > 0 && (
            <>
              <MenuSeparator />
              <MenuLabel>Move to</MenuLabel>
              {moveTargets.map((p) => (
                <MenuItem key={p.id || 'none'} icon={p.id ? Folder : FolderInput} onSelect={() => onMove(s.id, p.id)}>{p.name}</MenuItem>
              ))}
            </>
          )}
          <MenuSeparator />
          <MenuItem icon={Trash2} danger onSelect={() => onDelete(s)}>Delete</MenuItem>
        </Menu>
      )}
    </div>
  )
}
