import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Folder, FolderPlus, X } from 'lucide-react'

// Small in-app dialogs (they also work inside the desktop WebView, where
// window.prompt/confirm are unavailable). Portalled to <body> so they escape
// the sidebar's stacking context.

export function Dialog({ children, onClose, width = 'max-w-md', label }) {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    requestAnimationFrame(() => ref.current?.querySelector('input, textarea, button[data-autofocus]')?.focus())
    return () => { window.removeEventListener('keydown', onKey); prev?.focus?.() }
  }, [onClose])
  return createPortal(
    <div className="fixed inset-0 z-[80] grid place-items-center p-5">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade-in" onClick={onClose} />
      <div ref={ref} role="dialog" aria-modal="true" aria-label={label}
        className={`relative popover w-full ${width} p-5 animate-pop-in`}>
        {children}
      </div>
    </div>,
    document.body,
  )
}

function Header({ icon: Icon, title, onClose }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      {Icon && <Icon className="w-4 h-4 text-accent" />}
      <h2 className="text-fg font-medium text-[15px]">{title}</h2>
      <button onClick={onClose} className="ml-auto btn-ghost p-1.5" aria-label="Close"><X className="w-4 h-4" /></button>
    </div>
  )
}

export function ConfirmDialog({ title, message, confirmLabel = 'Delete', onConfirm, onClose }) {
  return (
    <Dialog onClose={onClose} width="max-w-sm" label={title}>
      <h2 className="text-fg font-medium text-[15px]">{title}</h2>
      {message && <p className="text-muted text-[13px] mt-2 leading-relaxed">{message}</p>}
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="btn px-3 py-1.5 text-[13px]">Cancel</button>
        <button data-autofocus onClick={() => { onConfirm(); onClose() }} className="btn-danger px-3 py-1.5 text-[13px]">
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}

export function NewProjectDialog({ onCreate, onClose }) {
  const [name, setName] = useState('')
  const submit = (e) => { e.preventDefault(); if (name.trim()) { onCreate(name.trim()); onClose() } }
  return (
    <Dialog onClose={onClose} width="max-w-sm" label="New project">
      <Header icon={FolderPlus} title="New project" onClose={onClose} />
      <form onSubmit={submit}>
        <label htmlFor="new-project-name" className="text-faint text-xs">Name</label>
        <input id="new-project-name" value={name} onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Q3 research" className="input mt-1" />
        <p className="text-faint text-xs mt-2">Projects group chats and can carry shared instructions.</p>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="btn px-3 py-1.5 text-[13px]">Cancel</button>
          <button type="submit" disabled={!name.trim()} className="btn-primary px-3 py-1.5 text-[13px]">Create project</button>
        </div>
      </form>
    </Dialog>
  )
}

export function ProjectEditor({ project, onSave, onClose }) {
  const [name, setName] = useState(project.name || '')
  const [instructions, setInstructions] = useState(project.instructions || '')
  const save = () => { onSave(project.id, { name: name.trim() || project.name, instructions }); onClose() }
  return (
    <Dialog onClose={onClose} label="Project settings">
      <Header icon={Folder} title="Project settings" onClose={onClose} />
      <label htmlFor="proj-name" className="text-faint text-xs">Name</label>
      <input id="proj-name" value={name} onChange={(e) => setName(e.target.value)} className="input mt-1" />
      <label htmlFor="proj-instr" className="block text-faint text-xs mt-4">Instructions</label>
      <p className="text-faint text-xs mt-0.5 mb-1.5">Added as context to every task in this project.</p>
      <textarea id="proj-instr" value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={5}
        placeholder="e.g. Answer concisely. Prefer Python. Cite sources."
        className="input resize-none leading-relaxed" />
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="btn px-3 py-1.5 text-[13px]">Cancel</button>
        <button onClick={save} className="btn-primary px-3 py-1.5 text-[13px]">Save</button>
      </div>
    </Dialog>
  )
}
