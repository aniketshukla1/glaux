import React, { useState } from 'react'
import {
  Plus, MessageSquarePlus, Folder, FolderPlus, Pencil, Trash2, PanelLeftClose,
  PanelLeft, ChevronDown, MessageSquare,
} from 'lucide-react'
import AthenaMark from './AthenaMark.jsx'

function SessionRow({ s, active, onSelect, onRename, onDelete }) {
  return (
    <div
      onClick={() => onSelect(s.id)}
      className={`group flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer text-sm transition ${
        active ? 'bg-line/10 text-fg' : 'text-muted hover:text-fg hover:bg-line/6'
      }`}
    >
      <MessageSquare className="w-3.5 h-3.5 shrink-0 text-faint" />
      <span className="flex-1 truncate">{s.title}</span>
      <span className="hidden group-hover:flex items-center gap-0.5 shrink-0">
        <button
          onClick={(e) => { e.stopPropagation(); onRename(s) }}
          className="p-1 rounded hover:bg-line/15 text-faint hover:text-fg" aria-label="Rename"
        >
          <Pencil className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(s) }}
          className="p-1 rounded hover:bg-line/15 text-faint hover:text-rose-400" aria-label="Delete session"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </span>
    </div>
  )
}

export default function Sidebar({
  workspace, collapsed, onToggleCollapse, onSelectSession, onNewSession,
  onRenameSession, onDeleteSession, onNewProject, onDeleteProject,
}) {
  const { projects = [], sessions = [], active_id } = workspace || {}
  const [openProjects, setOpenProjects] = useState({})

  const rename = (s) => {
    const t = window.prompt('Rename conversation', s.title)
    if (t && t.trim()) onRenameSession(s.id, t.trim())
  }
  const del = (s) => {
    if (window.confirm(`Delete "${s.title}"? This can't be undone.`)) onDeleteSession(s.id)
  }
  const newProject = () => {
    const name = window.prompt('New project name')
    if (name && name.trim()) onNewProject(name.trim())
  }

  const byProject = (pid) => sessions.filter((s) => s.project_id === pid)
  const ungrouped = sessions.filter((s) => !s.project_id)

  if (collapsed) {
    return (
      <div className="w-14 shrink-0 border-r border-line/10 flex flex-col items-center py-4 gap-3">
        <button onClick={onToggleCollapse} className="btn p-2" aria-label="Expand sidebar">
          <PanelLeft className="w-4 h-4" />
        </button>
        <button onClick={() => onNewSession()} className="btn-accent p-2" aria-label="New session" title="New session">
          <Plus className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <aside className="w-64 shrink-0 border-r border-line/10 flex flex-col h-screen sticky top-0">
      <div className="flex items-center gap-2 px-3 h-14 shrink-0">
        <div className="w-7 h-7 rounded-lg bg-accent/15 border border-accent/30 grid place-items-center">
          <AthenaMark className="w-5 h-5" />
        </div>
        <span className="text-fg font-medium tracking-tight">Athena</span>
        <button onClick={onToggleCollapse} className="ml-auto btn p-1.5" aria-label="Collapse sidebar">
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <div className="px-2.5 pb-2 flex gap-2">
        <button onClick={() => onNewSession()} className="btn-accent flex-1 px-3 py-2 text-sm flex items-center justify-center gap-2">
          <MessageSquarePlus className="w-4 h-4" /> New session
        </button>
        <button onClick={newProject} className="btn p-2" aria-label="New project" title="New project">
          <FolderPlus className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
        {projects.map((p) => {
          const open = openProjects[p.id] !== false
          const list = byProject(p.id)
          return (
            <div key={p.id} className="mt-2">
              <div className="group flex items-center gap-1.5 px-1.5 py-1 text-xs uppercase tracking-wide text-faint">
                <button onClick={() => setOpenProjects((o) => ({ ...o, [p.id]: !open }))} className="flex items-center gap-1.5 flex-1 min-w-0">
                  <ChevronDown className={`w-3 h-3 transition ${open ? '' : '-rotate-90'}`} />
                  <Folder className="w-3.5 h-3.5" />
                  <span className="truncate normal-case text-muted text-sm">{p.name}</span>
                </button>
                <button onClick={() => onNewSession(p.id)} className="hidden group-hover:block p-0.5 hover:text-fg" aria-label="New session in project" title="New session">
                  <Plus className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => { if (window.confirm(`Delete project "${p.name}"? Its chats become ungrouped.`)) onDeleteProject(p.id) }} className="hidden group-hover:block p-0.5 hover:text-rose-400" aria-label="Delete project">
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
              {open && (
                <div className="pl-2 space-y-0.5">
                  {list.length === 0 ? (
                    <div className="px-2.5 py-1.5 text-xs text-faint">No chats yet</div>
                  ) : (
                    list.map((s) => (
                      <SessionRow key={s.id} s={s} active={s.id === active_id} onSelect={onSelectSession} onRename={rename} onDelete={del} />
                    ))
                  )}
                </div>
              )}
            </div>
          )
        })}

        {ungrouped.length > 0 && (
          <div className="mt-2">
            <div className="px-1.5 py-1 text-xs uppercase tracking-wide text-faint">Chats</div>
            <div className="space-y-0.5">
              {ungrouped.map((s) => (
                <SessionRow key={s.id} s={s} active={s.id === active_id} onSelect={onSelectSession} onRename={rename} onDelete={del} />
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
