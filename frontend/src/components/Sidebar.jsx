import React, { useState } from 'react'
import {
  Plus, Search, MessagesSquare, ShieldCheck, ShieldAlert, Library, Activity, Folder, FolderPlus,
  ChevronRight, PanelLeftClose, PanelLeft, Settings, Keyboard, LogOut, Palette, MoreHorizontal,
  SlidersHorizontal, Trash2, X,
} from 'lucide-react'
import GlauxMark from './GlauxMark.jsx'
import UserAvatar from './UserAvatar.jsx'
import SessionRow from './sidebar/SessionRow.jsx'
import { ConfirmDialog, NewProjectDialog, ProjectEditor } from './sidebar/Dialogs.jsx'
import { Menu, MenuItem, MenuLabel, MenuSeparator } from './ui/Menu.jsx'
import { BRAND } from '../lib/brand.js'

export const THEMES = ['dark', 'light', 'oled', 'midnight', 'nord', 'ember']
const cap = (s) => s[0].toUpperCase() + s.slice(1)

// Top-level views are peers, always on screen, with a visible active state.
const NAV = [
  { key: 'chats', label: 'Chats', Icon: MessagesSquare },
  { key: 'proof', label: 'Proof', Icon: ShieldCheck },
  { key: 'library', label: 'Library', Icon: Library },
  { key: 'insights', label: 'Insights', Icon: Activity },
]

function NavItem({ item, active, onClick, badge, compact }) {
  const { Icon, label } = item
  return (
    <button onClick={onClick} aria-current={active ? 'page' : undefined} title={compact ? label : undefined}
      className={`w-full flex items-center gap-2.5 rounded-md text-[13px] transition-colors ${
        compact ? 'justify-center p-2' : 'px-2.5 py-1.5'
      } ${active ? 'bg-line/[0.09] text-fg font-medium' : 'text-muted hover:text-fg hover:bg-line/[0.05]'}`}>
      <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-accent' : ''}`} />
      {!compact && <span className="flex-1 text-left">{label}</span>}
      {!compact && badge}
    </button>
  )
}

function Section({ title, action, children, dropProps, highlight }) {
  return (
    <div {...dropProps} className={`rounded-md transition ${highlight ? 'ring-1 ring-accent/50 bg-accent/5' : ''}`}>
      <div className="flex items-center px-2.5 pt-3 pb-1">
        <span className="eyebrow flex-1">{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

export default function Sidebar({
  workspace, collapsed, onToggleCollapse, view, onNavigate, ledger,
  onSelectSession, onNewSession, onRenameSession, onDeleteSession,
  onNewProject, onUpdateProject, onDeleteProject, onMoveSession, onPinSession, loading,
  user, theme, onSetTheme, onOpenSettings, onOpenPalette, onOpenShortcuts, onSignOut,
  mobileOpen, onCloseMobile,
}) {
  const { projects = [], sessions = [], active_id } = workspace || {}
  const [openProjects, setOpenProjects] = useState({})
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [newProject, setNewProject] = useState(false)
  const [dragOver, setDragOver] = useState(undefined)  // undefined = none, null = ungrouped, id = project

  const dropProps = (pid) => ({
    onDragOver: (e) => { if (!e.dataTransfer.types.includes('text/glaux-session')) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (dragOver !== pid) setDragOver(pid) },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver((v) => (v === pid ? undefined : v)) },
    onDrop: (e) => {
      e.preventDefault()
      const sid = e.dataTransfer.getData('text/glaux-session')
      if (sid) onMoveSession(sid, pid)
      setDragOver(undefined)
    },
  })

  const selectSession = (id) => { onSelectSession(id); onCloseMobile?.() }
  const navigate = (key) => { onNavigate(key); onCloseMobile?.() }
  const delSession = (s) => setConfirm({
    title: 'Delete conversation?',
    message: `“${s.title}” and its history will be removed. The signed ledger keeps its record.`,
    onConfirm: () => onDeleteSession(s.id),
  })
  const delProject = (p) => setConfirm({
    title: 'Delete project?',
    message: `“${p.name}” will be removed. Its chats move to Recent.`,
    onConfirm: () => onDeleteProject(p.id),
  })

  const pinned = sessions.filter((s) => s.pinned)
  const byProject = (pid) => sessions.filter((s) => s.project_id === pid && !s.pinned)
  const recent = sessions.filter((s) => !s.project_id && !s.pinned)
  const inChats = view === 'chats'
  const rowProps = { projects, onSelect: selectSession, onRename: onRenameSession, onDelete: delSession, onMove: onMoveSession, onPin: onPinSession }

  const verified = ledger?.verification ? ledger.verification.valid : null
  const proofBadge = ledger?.count > 0 && (
    <span className={`flex items-center gap-1 text-[11px] tabular-nums ${verified === false ? 'text-bad' : 'text-faint'}`}
      title={verified === false ? 'Chain tampered' : `${ledger.count} signed blocks, verified`}>
      {verified === false ? <ShieldAlert className="w-3 h-3" /> : <span className="w-1.5 h-1.5 rounded-full bg-ok" />}
      {ledger.count}
    </span>
  )

  const userMenu = (compact) => (
    <Menu side="top" align="start" width="w-60" className={compact ? '' : 'w-full'}
      trigger={(t) => (
        <button {...t} aria-label="Account and settings"
          className={`flex items-center gap-2.5 rounded-md hover:bg-line/[0.06] transition ${compact ? 'p-1.5' : 'w-full px-2 py-1.5'}`}>
          <UserAvatar user={user} size={26} />
          {!compact && (
            <>
              <span className="flex-1 min-w-0 text-left">
                <span className="block text-[13px] text-fg truncate">{user?.name || 'Account'}</span>
                <span className="block text-[11px] text-faint truncate">{user?.email}</span>
              </span>
              <MoreHorizontal className="w-4 h-4 text-faint shrink-0" />
            </>
          )}
        </button>
      )}>
      <MenuItem icon={Settings} hint="⌘," onSelect={() => onOpenSettings('general')}>Settings</MenuItem>
      <MenuItem icon={Keyboard} hint="?" onSelect={onOpenShortcuts}>Keyboard shortcuts</MenuItem>
      <MenuSeparator />
      <MenuLabel><span className="inline-flex items-center gap-1.5"><Palette className="w-3 h-3" /> Theme</span></MenuLabel>
      {THEMES.map((t) => <MenuItem key={t} checked={theme === t} onSelect={() => onSetTheme(t)}>{cap(t)}</MenuItem>)}
      <MenuSeparator />
      <MenuItem icon={LogOut} onSelect={onSignOut}>Sign out</MenuItem>
    </Menu>
  )

  // ── collapsed rail (desktop) ────────────────────────────────────────────
  if (collapsed && !mobileOpen) {
    return (
      <aside className="hidden md:flex w-[52px] shrink-0 border-r border-line/[0.08] bg-sidebar flex-col items-center py-3 gap-1 h-screen sticky top-0">
        <button onClick={onToggleCollapse} className="btn-ghost p-2" aria-label="Expand sidebar" title="Expand sidebar (⌘B)"><PanelLeft className="w-4 h-4" /></button>
        <button onClick={() => onNewSession()} className="btn-accent p-2 mt-1" aria-label="New chat" title="New chat"><Plus className="w-4 h-4" /></button>
        <button onClick={onOpenPalette} className="btn-ghost p-2" aria-label="Search" title="Search (⌘K)"><Search className="w-4 h-4" /></button>
        <div className="w-6 h-px bg-line/10 my-1.5" />
        {NAV.map((n) => <NavItem key={n.key} item={n} compact active={view === n.key} onClick={() => onNavigate(n.key)} />)}
        <div className="mt-auto">{userMenu(true)}</div>
      </aside>
    )
  }

  return (
    <>
      {mobileOpen && <div className="md:hidden fixed inset-0 z-40 bg-black/50 animate-fade-in" onClick={onCloseMobile} />}
      <aside className={`w-[248px] shrink-0 border-r border-line/[0.08] bg-sidebar flex flex-col h-screen top-0 ${
        mobileOpen ? 'fixed left-0 z-50 shadow-2xl animate-fade-in' : 'hidden md:flex sticky'
      }`}>
        <div className="flex items-center gap-2 px-3 h-12 shrink-0">
          <GlauxMark size={22} />
          <span className="text-fg font-semibold tracking-tight text-[14px]">{BRAND}</span>
          {mobileOpen ? (
            <button onClick={onCloseMobile} className="ml-auto btn-ghost p-1.5" aria-label="Close menu"><X className="w-4 h-4" /></button>
          ) : (
            <button onClick={onToggleCollapse} className="ml-auto btn-ghost p-1.5" aria-label="Collapse sidebar" title="Collapse sidebar (⌘B)"><PanelLeftClose className="w-4 h-4" /></button>
          )}
        </div>

        <div className="px-2 space-y-1 shrink-0">
          <button onClick={() => { onNewSession(); onCloseMobile?.() }}
            className="btn-accent w-full px-2.5 py-1.5 text-[13px] !justify-start">
            <Plus className="w-4 h-4" />
            <span className="flex-1 text-left font-medium">New chat</span>
          </button>
          <button onClick={onOpenPalette}
            className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] text-faint hover:text-muted border border-line/[0.1] bg-bg/40 hover:bg-line/[0.04] transition">
            <Search className="w-4 h-4" />
            <span className="flex-1 text-left">Search</span>
            <span className="kbd">⌘K</span>
          </button>
        </div>

        <nav aria-label="Main" className="px-2 pt-3 space-y-0.5 shrink-0">
          {NAV.map((n) => (
            <NavItem key={n.key} item={n} active={view === n.key} onClick={() => navigate(n.key)}
              badge={n.key === 'proof' ? proofBadge : null} />
          ))}
        </nav>

        <div className="mx-3 mt-3 h-px bg-line/[0.08] shrink-0" />

        <div className="flex-1 overflow-y-auto px-2 pb-3" aria-label="Conversations">
          {loading ? (
            <div className="space-y-1.5 px-1 pt-3">
              {[78, 62, 70, 54, 66].map((w, i) => <div key={i} className="h-6 rounded-md shimmer bg-line/[0.06]" style={{ width: `${w}%` }} />)}
            </div>
          ) : (
            <>
              {pinned.length > 0 && (
                <Section title="Pinned">
                  <div className="space-y-px">{pinned.map((s) => <SessionRow key={s.id} s={s} active={s.id === active_id && inChats} {...rowProps} />)}</div>
                </Section>
              )}

              <Section title="Projects" action={
                <button onClick={() => setNewProject(true)} className="btn-ghost p-0.5 -mr-1" aria-label="New project" title="New project">
                  <FolderPlus className="w-3.5 h-3.5" />
                </button>
              }>
                {projects.length === 0 ? (
                  <button onClick={() => setNewProject(true)} className="w-full text-left px-2.5 py-1 text-[12px] text-faint hover:text-muted">
                    Group chats into a project…
                  </button>
                ) : projects.map((p) => {
                  const open = openProjects[p.id] !== false
                  const list = byProject(p.id)
                  return (
                    <div key={p.id} {...dropProps(p.id)}
                      className={`rounded-md transition ${dragOver === p.id ? 'ring-1 ring-accent/50 bg-accent/5' : ''}`}>
                      <div className="group flex items-center rounded-md text-muted hover:text-fg hover:bg-line/[0.05]">
                        <button onClick={() => setOpenProjects((o) => ({ ...o, [p.id]: !open }))} aria-expanded={open}
                          className="flex-1 min-w-0 flex items-center gap-1.5 pl-1.5 pr-1 py-[5px] text-[13px]">
                          <ChevronRight className={`w-3 h-3 shrink-0 text-faint transition-transform ${open ? 'rotate-90' : ''}`} />
                          <Folder className="w-3.5 h-3.5 shrink-0 text-faint" />
                          <span className="truncate">{p.name}</span>
                          <span className="ml-auto text-[11px] text-faint tabular-nums">{list.length || ''}</span>
                        </button>
                        <Menu align="end" width="w-48" className="shrink-0"
                          trigger={(t) => (
                            <button {...t} aria-label={`Actions for project ${p.name}`}
                              className={`mr-1 p-1 rounded text-faint hover:text-fg hover:bg-line/10 ${t.open ? '' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'}`}>
                              <MoreHorizontal className="w-3.5 h-3.5" />
                            </button>
                          )}>
                          <MenuItem icon={Plus} onSelect={() => onNewSession(p.id)}>New chat in project</MenuItem>
                          <MenuItem icon={SlidersHorizontal} onSelect={() => setEditing(p)}>Project settings</MenuItem>
                          <MenuSeparator />
                          <MenuItem icon={Trash2} danger onSelect={() => delProject(p)}>Delete project</MenuItem>
                        </Menu>
                      </div>
                      {open && (
                        <div className="ml-3 pl-1.5 border-l border-line/[0.08] space-y-px">
                          {list.length === 0
                            ? <div className="px-2.5 py-1 text-[12px] text-faint">Drag chats here</div>
                            : list.map((s) => <SessionRow key={s.id} s={s} active={s.id === active_id && inChats} {...rowProps} />)}
                        </div>
                      )}
                    </div>
                  )
                })}
              </Section>

              <Section title="Recent" dropProps={dropProps(null)} highlight={dragOver === null}>
                {recent.length === 0 ? (
                  <div className="px-2.5 py-1 text-[12px] text-faint">{sessions.length ? 'All chats are in projects' : 'No chats yet'}</div>
                ) : (
                  <div className="space-y-px">{recent.map((s) => <SessionRow key={s.id} s={s} active={s.id === active_id && inChats} {...rowProps} />)}</div>
                )}
              </Section>
            </>
          )}
        </div>

        <div className="p-2 border-t border-line/[0.08] shrink-0">{userMenu(false)}</div>

        {editing && <ProjectEditor project={editing} onSave={onUpdateProject} onClose={() => setEditing(null)} />}
        {newProject && <NewProjectDialog onCreate={onNewProject} onClose={() => setNewProject(false)} />}
        {confirm && <ConfirmDialog {...confirm} onClose={() => setConfirm(null)} />}
      </aside>
    </>
  )
}
