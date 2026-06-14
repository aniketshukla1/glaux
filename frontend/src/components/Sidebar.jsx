import React, { useEffect, useRef, useState } from 'react'
import {
  Plus, MessageSquarePlus, Folder, FolderPlus, FolderInput, Pencil, Trash2,
  PanelLeftClose, PanelLeft, ChevronDown, MessageSquare, SlidersHorizontal, X,
} from 'lucide-react'
import AthenaMark from './AthenaMark.jsx'

// --- modals (in-app, so they work inside the desktop WebView) -------------

function Modal({ children, onClose, width = 'max-w-md' }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center p-5">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={`relative card w-full ${width} p-5`}>{children}</div>
    </div>
  )
}

function ConfirmDialog({ title, message, confirmLabel = 'Delete', onConfirm, onClose }) {
  return (
    <Modal onClose={onClose} width="max-w-sm">
      <h2 className="text-fg font-medium">{title}</h2>
      {message && <p className="text-muted text-sm mt-2">{message}</p>}
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="btn px-3 py-2 text-sm">Cancel</button>
        <button
          onClick={() => { onConfirm(); onClose() }}
          className="px-3 py-2 text-sm rounded-lg border border-rose-500/40 text-rose-400 bg-rose-500/10 hover:bg-rose-500/20"
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

function NewProjectDialog({ onCreate, onClose }) {
  const [name, setName] = useState('')
  const submit = (e) => { e.preventDefault(); if (name.trim()) { onCreate(name.trim()); onClose() } }
  return (
    <Modal onClose={onClose} width="max-w-sm">
      <div className="flex items-center gap-2 mb-3">
        <FolderPlus className="w-4 h-4 text-accent" />
        <h2 className="text-fg font-medium">New project</h2>
        <button onClick={onClose} className="ml-auto btn p-1.5" aria-label="Close"><X className="w-4 h-4" /></button>
      </div>
      <form onSubmit={submit}>
        <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name"
          className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint" />
        <div className="flex justify-end gap-2 mt-4">
          <button type="button" onClick={onClose} className="btn px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={!name.trim()} className="btn-accent px-3 py-2 text-sm disabled:opacity-50">Create</button>
        </div>
      </form>
    </Modal>
  )
}

function ProjectEditor({ project, onSave, onClose }) {
  const [name, setName] = useState(project.name || '')
  const [instructions, setInstructions] = useState(project.instructions || '')
  const save = () => { onSave(project.id, { name: name.trim() || project.name, instructions }); onClose() }
  return (
    <Modal onClose={onClose}>
      <div className="flex items-center gap-2">
        <Folder className="w-4 h-4 text-accent" />
        <h2 className="text-fg font-medium">Customize project</h2>
        <button onClick={onClose} className="ml-auto btn p-1.5" aria-label="Close"><X className="w-4 h-4" /></button>
      </div>
      <div className="mt-4">
        <label className="text-faint text-xs">Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="w-full mt-1 glass px-3 py-2 bg-transparent outline-none text-sm text-fg" />
      </div>
      <div className="mt-4">
        <label className="text-faint text-xs">Custom instructions</label>
        <p className="text-faint text-xs mt-0.5 mb-1.5">Prepended as context to every task in this project's chats.</p>
        <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={5}
          placeholder="e.g. Answer concisely. Prefer Python. Cite sources."
          className="w-full glass px-3 py-2 bg-transparent outline-none text-sm text-fg placeholder:text-faint resize-none" />
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="btn px-3 py-2 text-sm">Cancel</button>
        <button onClick={save} className="btn-accent px-3 py-2 text-sm">Save</button>
      </div>
    </Modal>
  )
}

// --- session row ----------------------------------------------------------

function MoveMenu({ projects, currentProjectId, onMove, onClose }) {
  const options = [
    ...(currentProjectId ? [{ id: null, name: 'No project' }] : []),
    ...projects.filter((p) => p.id !== currentProjectId).map((p) => ({ id: p.id, name: p.name })),
  ]
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); onClose() }} />
      <div className="absolute right-0 top-full mt-1 z-50 w-44 card p-1 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-2 py-1 text-[11px] uppercase tracking-wide text-faint">Move to</div>
        {options.length === 0 ? (
          <div className="px-2 py-1.5 text-xs text-faint">No projects yet</div>
        ) : (
          options.map((o) => (
            <button key={o.id || 'none'} onClick={(e) => { e.stopPropagation(); onMove(o.id); onClose() }}
              className="w-full text-left px-2 py-1.5 rounded text-sm text-muted hover:text-fg hover:bg-line/10 truncate">
              {o.name}
            </button>
          ))
        )}
      </div>
    </>
  )
}

function SessionRow({ s, active, projects, onSelect, onRename, onDelete, onMove }) {
  const [moveOpen, setMoveOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(s.title)
  const inputRef = useRef(null)

  const startEdit = () => { setVal(s.title); setEditing(true) }
  const commit = () => { setEditing(false); const t = val.trim(); if (t && t !== s.title) onRename(s.id, t) }
  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])

  return (
    <div
      onClick={() => !editing && onSelect(s.id)}
      className={`group relative flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer text-sm transition ${
        active ? 'bg-line/10 text-fg' : 'text-muted hover:text-fg hover:bg-line/6'
      }`}
    >
      <MessageSquare className="w-3.5 h-3.5 shrink-0 text-faint" />
      {editing ? (
        <input
          ref={inputRef}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
          onBlur={commit}
          className="flex-1 min-w-0 bg-transparent outline-none text-fg border-b border-accent/40"
        />
      ) : (
        <span className="flex-1 truncate">{s.title}</span>
      )}
      {!editing && (
        <span className={`items-center gap-0.5 shrink-0 ${moveOpen ? 'flex' : 'hidden group-hover:flex'}`}>
          <button onClick={(e) => { e.stopPropagation(); setMoveOpen((o) => !o) }} className="p-1 rounded hover:bg-line/15 text-faint hover:text-fg" aria-label="Move to project">
            <FolderInput className="w-3 h-3" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); startEdit() }} className="p-1 rounded hover:bg-line/15 text-faint hover:text-fg" aria-label="Rename">
            <Pencil className="w-3 h-3" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); onDelete(s) }} className="p-1 rounded hover:bg-line/15 text-faint hover:text-rose-400" aria-label="Delete session">
            <Trash2 className="w-3 h-3" />
          </button>
        </span>
      )}
      {moveOpen && (
        <MoveMenu projects={projects} currentProjectId={s.project_id} onMove={(pid) => onMove(s.id, pid)} onClose={() => setMoveOpen(false)} />
      )}
    </div>
  )
}

export default function Sidebar({
  workspace, collapsed, onToggleCollapse, onSelectSession, onNewSession,
  onRenameSession, onDeleteSession, onNewProject, onUpdateProject, onDeleteProject, onMoveSession,
}) {
  const { projects = [], sessions = [], active_id } = workspace || {}
  const [openProjects, setOpenProjects] = useState({})
  const [editing, setEditing] = useState(null)        // project being customized
  const [confirm, setConfirm] = useState(null)        // { title, message, onConfirm }
  const [newProject, setNewProject] = useState(false)

  const delSession = (s) => setConfirm({
    title: 'Delete conversation?',
    message: `"${s.title}" and its history will be removed. This can't be undone.`,
    onConfirm: () => onDeleteSession(s.id),
  })
  const delProject = (p) => setConfirm({
    title: 'Delete project?',
    message: `"${p.name}" will be removed and its chats become ungrouped.`,
    onConfirm: () => onDeleteProject(p.id),
  })

  const byProject = (pid) => sessions.filter((s) => s.project_id === pid)
  const ungrouped = sessions.filter((s) => !s.project_id)
  const rowProps = { projects, onSelect: onSelectSession, onRename: onRenameSession, onDelete: delSession, onMove: onMoveSession }

  if (collapsed) {
    return (
      <div className="w-14 shrink-0 border-r border-line/10 flex flex-col items-center py-4 gap-3">
        <button onClick={onToggleCollapse} className="btn p-2" aria-label="Expand sidebar"><PanelLeft className="w-4 h-4" /></button>
        <button onClick={() => onNewSession()} className="btn-accent p-2" aria-label="New session" title="New session"><Plus className="w-4 h-4" /></button>
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
        <button onClick={onToggleCollapse} className="ml-auto btn p-1.5" aria-label="Collapse sidebar"><PanelLeftClose className="w-4 h-4" /></button>
      </div>

      <div className="px-2.5 pb-2 flex gap-2">
        <button onClick={() => onNewSession()} className="btn-accent flex-1 px-3 py-2 text-sm flex items-center justify-center gap-2">
          <MessageSquarePlus className="w-4 h-4" /> New session
        </button>
        <button onClick={() => setNewProject(true)} className="btn p-2" aria-label="New project" title="New project"><FolderPlus className="w-4 h-4" /></button>
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
                <button onClick={() => onNewSession(p.id)} className="hidden group-hover:block p-0.5 hover:text-fg" aria-label="New session in project" title="New session"><Plus className="w-3.5 h-3.5" /></button>
                <button onClick={() => setEditing(p)} className="hidden group-hover:block p-0.5 hover:text-fg" aria-label="Customize project" title="Customize"><SlidersHorizontal className="w-3 h-3" /></button>
                <button onClick={() => delProject(p)} className="hidden group-hover:block p-0.5 hover:text-rose-400" aria-label="Delete project"><Trash2 className="w-3 h-3" /></button>
              </div>
              {open && (
                <div className="pl-2 space-y-0.5">
                  {list.length === 0 ? (
                    <div className="px-2.5 py-1.5 text-xs text-faint">No chats yet</div>
                  ) : (
                    list.map((s) => <SessionRow key={s.id} s={s} active={s.id === active_id} {...rowProps} />)
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
              {ungrouped.map((s) => <SessionRow key={s.id} s={s} active={s.id === active_id} {...rowProps} />)}
            </div>
          </div>
        )}
      </div>

      {editing && <ProjectEditor project={editing} onSave={onUpdateProject} onClose={() => setEditing(null)} />}
      {newProject && <NewProjectDialog onCreate={onNewProject} onClose={() => setNewProject(false)} />}
      {confirm && <ConfirmDialog {...confirm} onClose={() => setConfirm(null)} />}
    </aside>
  )
}
