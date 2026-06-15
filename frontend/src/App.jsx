import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { MessageSquarePlus, MessageSquare, LayoutGrid, Settings as SettingsIcon, Palette, PanelLeft } from 'lucide-react'
import {
  getHealth, getLedger, getAgents, getSafety, setSafety, getApproval, setApproval,
  getAuth, dispatchTask, getWorkspace, getSession, createSession, activateSession,
  updateSession, deleteSession, createProject, updateProject, deleteProject,
} from './api.js'
import TopBar from './components/TopBar.jsx'
import Sidebar from './components/Sidebar.jsx'
import RunView from './components/RunView.jsx'
import Studio from './components/Studio.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import CommandPalette from './components/CommandPalette.jsx'

const PALETTE_THEMES = ['dark', 'light', 'oled', 'midnight', 'nord', 'ember']

const mergeBlocks = (a, b) => {
  const seen = new Set(a.map((x) => x.index))
  return [...a, ...b.filter((x) => !seen.has(x.index))].sort((x, y) => x.index - y.index)
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('athena-theme') || 'dark')
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('athena-sidebar') === 'collapsed')
  const [studioOpen, setStudioOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)

  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [agentsMap, setAgentsMap] = useState({})
  const [safety, setSafetyMode] = useState('live')
  const [approval, setApprovalMode] = useState('auto')
  const [auth, setAuth] = useState({ enabled: false })
  const [error, setError] = useState(null)

  const [workspace, setWorkspace] = useState({ projects: [], sessions: [], active_id: null })
  const [activeSession, setActiveSession] = useState(null)
  const [liveBlocks, setLiveBlocks] = useState([])
  const [goal, setGoal] = useState(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('athena-theme', theme)
  }, [theme])

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((o) => !o) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const toggleCollapse = () => setCollapsed((c) => {
    localStorage.setItem('athena-sidebar', c ? 'expanded' : 'collapsed')
    return !c
  })

  const refresh = useCallback(async () => {
    try {
      const [l, h, a, s, ap, au] = [
        await getLedger(), await getHealth(), await getAgents(),
        await getSafety(), await getApproval(), await getAuth(),
      ]
      setLedger(l); setHealth(h)
      setAgentsMap(Object.fromEntries(a.agents.map((x) => [x.agent_id, x.role])))
      setSafetyMode(s.mode); setApprovalMode(ap.mode); setAuth(au); setError(null)
    } catch {
      setError('Backend unreachable — start it with:  athena up')
    }
  }, [])

  const loadWorkspace = useCallback(async () => {
    try { const w = await getWorkspace(); setWorkspace(w); return w } catch { return null }
  }, [])

  const loadSession = useCallback(async (id) => {
    if (!id) return
    try { const { session } = await getSession(id); setActiveSession(session) } catch {}
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh])

  useEffect(() => {
    (async () => { const w = await loadWorkspace(); if (w?.active_id) loadSession(w.active_id) })()
  }, [loadWorkspace, loadSession])

  // live block streaming
  useEffect(() => {
    let ws, retry, closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'block') setLiveBlocks((prev) => mergeBlocks(prev, [msg.block]))
      }
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2000) }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => { closed = true; clearTimeout(retry); if (ws) ws.close() }
  }, [])

  const roleOf = useCallback((id) => agentsMap[id], [agentsMap])
  const clearLive = () => { setGoal(null); setResult(null); setLiveBlocks([]) }

  const onDispatch = async (directive) => {
    setGoal(directive); setRunning(true); setResult(null); setLiveBlocks([])
    try {
      const r = await dispatchTask(directive)
      setResult(r)
      setLiveBlocks((prev) => mergeBlocks(prev, r.new_blocks || []))
      await refresh()
      await loadSession(r.session_id || workspace.active_id)
      await loadWorkspace()
      clearLive() // the completed run is now in the session history; drop the transient turn
    } catch (e) {
      setError(`Dispatch failed: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  const selectSession = async (id) => {
    if (id === workspace.active_id) return
    clearLive()
    try { await activateSession(id) } catch {}
    await loadSession(id)
    await loadWorkspace()
  }

  const newSession = async (projectId) => {
    clearLive()
    try { const { session } = await createSession(null, projectId); await loadSession(session.id) } catch {}
    await loadWorkspace()
  }

  const onRenameSession = async (id, title) => { try { await updateSession(id, { title }) } catch {}; await loadWorkspace(); if (id === activeSession?.id) loadSession(id) }
  const onDeleteSession = async (id) => {
    try {
      const res = await deleteSession(id)
      setWorkspace(res)
      if (id === activeSession?.id) { clearLive(); await loadSession(res.active_id) }
    } catch {}
  }
  const onNewProject = async (name) => { try { await createProject(name) } catch {}; await loadWorkspace() }
  const onUpdateProject = async (id, patch) => { try { await updateProject(id, patch) } catch {}; await loadWorkspace() }
  const onDeleteProject = async (id) => { try { const res = await deleteProject(id); setWorkspace(res) } catch {} }
  const onMoveSession = async (id, projectId) => {
    try { await updateSession(id, { project_id: projectId }) } catch {}
    await loadWorkspace()
    if (id === activeSession?.id) loadSession(id)
  }

  const onSafety = async (mode) => { try { setSafetyMode((await setSafety(mode)).mode) } catch {} }
  const onApproval = async (mode) => { try { setApprovalMode((await setApproval(mode)).mode) } catch {} }

  const verification = result?.verification || ledger.verification

  const commands = useMemo(() => {
    const cmds = [
      { id: 'new', section: 'Actions', label: 'New session', icon: MessageSquarePlus, run: () => newSession(), keywords: 'chat conversation' },
      { id: 'studio', section: 'Actions', label: 'Open Studio', icon: LayoutGrid, run: () => setStudioOpen(true), keywords: 'skills tools eval metrics memory ledger schedules' },
      { id: 'settings', section: 'Actions', label: 'Open Settings', icon: SettingsIcon, run: () => setSettingsOpen(true), keywords: 'model safety approval' },
      { id: 'sidebar', section: 'Actions', label: collapsed ? 'Expand sidebar' : 'Collapse sidebar', icon: PanelLeft, run: toggleCollapse },
      ...PALETTE_THEMES.map((t) => ({ id: `theme-${t}`, section: 'Theme', label: `Theme: ${t[0].toUpperCase()}${t.slice(1)}`, icon: Palette, run: () => setTheme(t), keywords: 'appearance color' })),
      ...(workspace.sessions || []).map((s) => ({ id: `sess-${s.id}`, section: 'Switch to', label: s.title, icon: MessageSquare, hint: s.id === workspace.active_id ? 'current' : '', run: () => selectSession(s.id), keywords: 'conversation chat open' })),
    ]
    return cmds
  }, [workspace, collapsed])

  return (
    <div className="flex min-h-screen">
      <Sidebar
        workspace={workspace}
        collapsed={collapsed}
        onToggleCollapse={toggleCollapse}
        onSelectSession={selectSession}
        onNewSession={newSession}
        onRenameSession={onRenameSession}
        onDeleteSession={onDeleteSession}
        onNewProject={onNewProject}
        onUpdateProject={onUpdateProject}
        onDeleteProject={onDeleteProject}
        onMoveSession={onMoveSession}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="sticky top-0 z-30 px-5 sm:px-8 bg-[rgb(var(--bg))]/85 backdrop-blur-md border-b border-line/8">
          <TopBar
            title={activeSession?.title}
            theme={theme}
            onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            onOpenStudio={() => setStudioOpen(true)}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenPalette={() => setPaletteOpen(true)}
            verified={ledger.verification ? ledger.verification.valid : null}
            health={health}
          />
          {error && (
            <div className="glass p-3 mb-4 text-sm" style={{ borderColor: 'rgb(244 63 94 / 0.4)', color: 'rgb(251 113 133)' }}>
              {error}
            </div>
          )}
        </div>

        <main className="flex-1">
          <RunView
            session={activeSession}
            blocks={liveBlocks}
            roleOf={roleOf}
            running={running}
            result={result}
            goal={goal}
            onDispatch={onDispatch}
            verification={verification}
          />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
      <Studio open={studioOpen} onClose={() => setStudioOpen(false)} ledger={ledger} blocks={liveBlocks} onVerify={refresh} />
      <SettingsPanel
        open={settingsOpen} onClose={() => setSettingsOpen(false)}
        theme={theme} onSetTheme={setTheme}
        safety={safety} onSafety={onSafety}
        approval={approval} onApproval={onApproval}
        auth={auth}
      />
    </div>
  )
}
