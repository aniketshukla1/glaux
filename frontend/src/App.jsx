import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { MessageSquarePlus, MessageSquare, LayoutGrid, Settings as SettingsIcon, Palette, PanelLeft, Loader2, Keyboard, Download, Copy, Mic, BookMarked } from 'lucide-react'
import { exportConversation, conversationToMarkdown } from './lib/export.js'
import {
  getHealth, getLedger, getAgents, getSafety, setSafety, getApproval, setApproval,
  getAuth, dispatchTask, stopTask, getWorkspace, getSession, createSession, activateSession,
  updateSession, deleteSession, pinSession, createProject, updateProject, deleteProject,
  createPersona, updatePersona, deletePersona,
  createRecipe, updateRecipe, deleteRecipe,
  getAuthState, updateProfile, changePassword, logoutEverywhere, deleteAccount,
  getToken, setToken, clearToken, verifyEmail, resendVerification,
} from './api.js'
import TopBar from './components/TopBar.jsx'
import Sidebar from './components/Sidebar.jsx'
import RunView from './components/RunView.jsx'
import Studio from './components/Studio.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import AuthScreen from './components/AuthScreen.jsx'
import ShortcutsHelp from './components/ShortcutsHelp.jsx'
import Messaging from './components/Messaging.jsx'
import VoiceWake from './components/VoiceWake.jsx'
import { recognitionSupported } from './lib/speech.js'

const PALETTE_THEMES = ['dark', 'light', 'oled', 'midnight', 'nord', 'ember']

const mergeBlocks = (a, b) => {
  const seen = new Set(a.map((x) => x.index))
  return [...a, ...b.filter((x) => !seen.has(x.index))].sort((x, y) => x.index - y.index)
}

// Desktop notification when a task finishes while the window is in the background.
const requestNotifyPermission = () => {
  try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission() } catch { /* ignore */ }
}
const notifyDone = (r) => {
  try {
    if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return
    const body = (r?.final || '').replace(/\s+/g, ' ').slice(0, 140) || (r?.success ? 'Task complete' : 'Task finished')
    const n = new Notification(r?.success ? 'Athena finished ✓' : 'Athena stopped', { body })
    n.onclick = () => { window.focus(); n.close() }
  } catch { /* ignore */ }
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('athena-theme') || 'dark')
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('athena-sidebar') === 'collapsed')
  const [studioOpen, setStudioOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState('appearance')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [messagingOpen, setMessagingOpen] = useState(false)
  const [wakeOn, setWakeOn] = useState(() => localStorage.getItem('athena-wake') === '1')
  useEffect(() => { localStorage.setItem('athena-wake', wakeOn ? '1' : '0') }, [wakeOn])

  // accounts / auth
  const [user, setUser] = useState(null)
  const [hasUsers, setHasUsers] = useState(true)
  const [authReady, setAuthReady] = useState(false)
  const [authState, setAuthState] = useState({ oauth: [], signup: 'open' })
  const [urlCtx, setUrlCtx] = useState({ reset: '', invite: '', oauthError: '' })
  const [verifyMsg, setVerifyMsg] = useState('')

  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [agentsMap, setAgentsMap] = useState({})
  const [safety, setSafetyMode] = useState('live')
  const [approval, setApprovalMode] = useState('auto')
  const [auth, setAuth] = useState({ enabled: false })
  const [error, setError] = useState(null)

  const [workspace, setWorkspace] = useState({ projects: [], sessions: [], active_id: null })
  const [wsLoading, setWsLoading] = useState(true)
  const [activeSession, setActiveSession] = useState(null)
  const [liveBlocks, setLiveBlocks] = useState([])
  const [goal, setGoal] = useState(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [streamingText, setStreamingText] = useState('')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('athena-theme', theme)
  }, [theme])

  // bootstrap auth: handle any auth links (oauth callback, verify, reset, invite),
  // then figure out who's signed in and what login options exist.
  useEffect(() => {
    (async () => {
      const params = new URLSearchParams(window.location.search)
      const tokenParam = params.get('token')      // returned by the OAuth callback
      const verifyParam = params.get('verify')
      const resetParam = params.get('reset')
      const inviteParam = params.get('invite')
      const oauthError = params.get('oauth_error')
      if (tokenParam) setToken(tokenParam)
      setUrlCtx({ reset: resetParam || '', invite: inviteParam || '', oauthError: oauthError ? decodeURIComponent(oauthError) : '' })
      if (tokenParam || verifyParam || resetParam || inviteParam || oauthError) {
        window.history.replaceState({}, document.title, window.location.pathname)  // tidy the URL
      }
      try {
        const s = await getAuthState()
        setAuthState(s); setHasUsers(s.has_users)
        if (s.authenticated && s.user) { setUser(s.user); if (s.user.settings?.theme) setTheme(s.user.settings.theme) }
      } catch { /* backend down — AuthScreen still shows */ }
      if (verifyParam) {
        try { const r = await verifyEmail(verifyParam); setUser((u) => (u ? r.user : u)); setVerifyMsg('Email verified ✓') }
        catch { /* invalid/expired link */ }
      }
      setAuthReady(true)
    })()
  }, [])

  const onResendVerification = async () => {
    try {
      const out = await resendVerification()
      if (out.dev_link) { window.location.href = out.dev_link; return }  // dev mode: link verifies on reload
      setVerifyMsg('Verification email sent — check your inbox.')
    } catch { /* ignore */ }
  }

  // a 401 anywhere drops us back to the sign-in screen
  useEffect(() => {
    const onUnauth = () => setUser(null)
    window.addEventListener('athena-unauthorized', onUnauth)
    return () => window.removeEventListener('athena-unauthorized', onUnauth)
  }, [])

  const onAuthed = useCallback((u) => {
    setUser(u); setHasUsers(true)
    if (u?.settings?.theme) setTheme(u.settings.theme)
  }, [])

  const applyTheme = (t) => {
    setTheme(t)
    if (user) updateProfile({ settings: { theme: t } }).then((r) => setUser(r.user)).catch(() => {})
  }

  const openSettings = (tab = 'appearance') => { setSettingsTab(tab); setSettingsOpen(true) }

  // account actions
  const onSignOut = () => { clearToken(); setUser(null); setSettingsOpen(false) }
  const onSignOutEverywhere = async () => { try { await logoutEverywhere() } catch { /* ignore */ } finally { onSignOut() } }
  const onUpdateProfile = async (patch) => {
    const r = await updateProfile(patch); setUser(r.user)
    if (patch.settings?.theme) setTheme(patch.settings.theme)
    return r.user
  }
  const onChangePassword = async (current, next) => {
    const out = await changePassword(current, next)
    if (out.token) setToken(out.token)  // password change rotated the token; keep this session alive
    if (out.user) setUser(out.user)
    return out
  }
  const onDeleteAccount = async () => { try { await deleteAccount() } catch { /* ignore */ } finally { onSignOut() } }

  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'TEXTAREA'].includes(e.target.tagName) || e.target.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((o) => !o) }
      else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        setCollapsed((c) => { localStorage.setItem('athena-sidebar', c ? 'expanded' : 'collapsed'); return !c })
      } else if (e.key === '?' && !typing) { e.preventDefault(); setHelpOpen((o) => !o) }
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
    finally { setWsLoading(false) }
  }, [])

  const loadSession = useCallback(async (id) => {
    if (!id) return
    try { const { session } = await getSession(id); setActiveSession(session) } catch {}
  }, [])

  useEffect(() => {
    if (!user) return
    refresh()
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh, user])

  useEffect(() => {
    if (!user) return
    (async () => { const w = await loadWorkspace(); if (w?.active_id) loadSession(w.active_id) })()
  }, [loadWorkspace, loadSession, user])

  // live block streaming
  useEffect(() => {
    if (!user) return
    let ws, retry, closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const tok = getToken()
      ws = new WebSocket(`${proto}://${location.host}/ws${tok ? `?token=${encodeURIComponent(tok)}` : ''}`)
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'block') setLiveBlocks((prev) => mergeBlocks(prev, [msg.block]))
        else if (msg.type === 'token' && msg.uid === user.id) setStreamingText((s) => s + msg.text)
      }
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2000) }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => { closed = true; clearTimeout(retry); if (ws) ws.close() }
  }, [user])

  const roleOf = useCallback((id) => agentsMap[id], [agentsMap])
  const clearLive = () => { setGoal(null); setResult(null); setLiveBlocks([]); setStreamingText('') }

  const onDispatch = async (directive) => {
    setGoal(directive); setRunning(true); setResult(null); setLiveBlocks([]); setStreamingText('')
    requestNotifyPermission()  // a dispatch is a user gesture, so we may ask here
    try {
      const r = await dispatchTask(directive)
      setResult(r)
      notifyDone(r)
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

  const onStop = async () => { try { await stopTask() } catch { /* ignore */ } }

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

  const onPinSession = async (id, pinned) => { try { await pinSession(id, pinned) } catch { /* ignore */ }; await loadWorkspace() }
  const onCreatePersona = async (data) => { await createPersona(data.name, data.instructions, data.emoji); await loadWorkspace() }
  const onUpdatePersona = async (id, data) => { await updatePersona(id, data); await loadWorkspace() }
  const onDeletePersona = async (id) => { try { const res = await deletePersona(id); setWorkspace(res) } catch { /* ignore */ } }
  const onCreateRecipe = async (data) => { await createRecipe(data); await loadWorkspace() }
  const onUpdateRecipe = async (id, data) => { await updateRecipe(id, data); await loadWorkspace() }
  const onDeleteRecipe = async (id) => { try { const res = await deleteRecipe(id); setWorkspace(res) } catch { /* ignore */ } }
  const onSetSessionPersona = async (personaId) => {
    if (!activeSession) return
    try { await updateSession(activeSession.id, { persona_id: personaId }) } catch { /* ignore */ }
    await loadWorkspace(); loadSession(activeSession.id)
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
      { id: 'help', section: 'Actions', label: 'Keyboard shortcuts', icon: Keyboard, run: () => setHelpOpen(true), keywords: 'keys hotkeys cheatsheet' },
      { id: 'recipes', section: 'Actions', label: 'Recipes', icon: BookMarked, run: () => openSettings('recipes'), keywords: 'workflow template saved prompt task' },
      ...(recognitionSupported() ? [{ id: 'wake', section: 'Actions', label: wakeOn ? 'Turn off hands-free voice' : 'Turn on hands-free voice', icon: Mic, run: () => setWakeOn((v) => !v), keywords: 'voice wake word hey athena dictation listen microphone' }] : []),
      ...(user?.is_admin ? [{ id: 'messaging', section: 'Actions', label: 'Messaging gateways', icon: MessageSquare, run: () => setMessagingOpen(true), keywords: 'telegram discord slack whatsapp signal channels bot' }] : []),
      ...(activeSession?.runs?.length ? [
        { id: 'export', section: 'Actions', label: 'Export conversation (Markdown)', icon: Download, run: () => exportConversation(activeSession), keywords: 'download save share md file' },
        { id: 'copy-convo', section: 'Actions', label: 'Copy conversation', icon: Copy, run: () => navigator.clipboard?.writeText(conversationToMarkdown(activeSession)), keywords: 'clipboard share markdown' },
      ] : []),
      ...PALETTE_THEMES.map((t) => ({ id: `theme-${t}`, section: 'Theme', label: `Theme: ${t[0].toUpperCase()}${t.slice(1)}`, icon: Palette, run: () => setTheme(t), keywords: 'appearance color' })),
      ...(workspace.sessions || []).map((s) => ({ id: `sess-${s.id}`, section: 'Switch to', label: s.title, icon: MessageSquare, hint: s.id === workspace.active_id ? 'current' : '', run: () => selectSession(s.id), keywords: 'conversation chat open' })),
    ]
    return cmds
  }, [workspace, collapsed, user, activeSession])

  if (!authReady) {
    return <div className="min-h-screen grid place-items-center"><Loader2 className="w-6 h-6 animate-spin text-muted" /></div>
  }
  if (!user) {
    return (
      <AuthScreen
        firstRun={!hasUsers}
        onAuthed={onAuthed}
        oauthProviders={authState.oauth}
        invite={urlCtx.invite}
        resetToken={urlCtx.reset}
        initialError={urlCtx.oauthError}
      />
    )
  }

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
        onPinSession={onPinSession}
        loading={wsLoading}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="sticky top-0 z-30 px-5 sm:px-8 bg-[rgb(var(--bg))]/85 backdrop-blur-md border-b border-line/8">
          <TopBar
            title={activeSession?.title}
            theme={theme}
            onToggleTheme={() => applyTheme(theme === 'dark' ? 'light' : 'dark')}
            onOpenStudio={() => setStudioOpen(true)}
            onOpenSettings={() => openSettings('appearance')}
            onOpenPalette={() => setPaletteOpen(true)}
            verified={ledger.verification ? ledger.verification.valid : null}
            health={health}
            user={user}
            onOpenAccount={() => openSettings('account')}
            onModelChanged={refresh}
            onOpenModel={() => openSettings('model')}
            personas={workspace.personas || []}
            activePersonaId={activeSession?.persona_id}
            onPickPersona={onSetSessionPersona}
            onManagePersonas={() => openSettings('personas')}
            wakeSupported={recognitionSupported()}
            wakeOn={wakeOn}
            onToggleWake={() => setWakeOn((v) => !v)}
          />
          {error && (
            <div className="glass p-3 mb-4 text-sm" style={{ borderColor: 'rgb(244 63 94 / 0.4)', color: 'rgb(251 113 133)' }}>
              {error}
            </div>
          )}
          {user && !user.email_verified && (
            <div className="glass p-2.5 mb-4 text-xs flex items-center gap-2 flex-wrap" style={{ borderColor: 'rgb(251 191 36 / 0.4)' }}>
              <span className="text-amber-300">Verify your email to secure your account — we sent a link to {user.email}.</span>
              <button onClick={onResendVerification} className="text-accent underline underline-offset-2">Resend</button>
              {verifyMsg && <span className="text-emerald-400">{verifyMsg}</span>}
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
            streamingText={streamingText}
            onDispatch={onDispatch}
            onStop={onStop}
            verification={verification}
            recipes={workspace.recipes || []}
          />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <Messaging open={messagingOpen} onClose={() => setMessagingOpen(false)} />
      <VoiceWake enabled={wakeOn} running={running} result={result} onDispatch={onDispatch} onDisable={() => setWakeOn(false)} />
      <Studio open={studioOpen} onClose={() => setStudioOpen(false)} ledger={ledger} blocks={liveBlocks} onVerify={refresh} user={user} onOpenMessaging={() => setMessagingOpen(true)} />
      <SettingsPanel
        open={settingsOpen} onClose={() => setSettingsOpen(false)}
        initialTab={settingsTab}
        health={health} onRefresh={refresh}
        theme={theme} onSetTheme={applyTheme}
        safety={safety} onSafety={onSafety}
        approval={approval} onApproval={onApproval}
        auth={auth}
        user={user}
        onUpdateProfile={onUpdateProfile}
        onChangePassword={onChangePassword}
        onSignOut={onSignOut}
        onSignOutEverywhere={onSignOutEverywhere}
        onDeleteAccount={onDeleteAccount}
        personas={workspace.personas || []}
        onCreatePersona={onCreatePersona}
        onUpdatePersona={onUpdatePersona}
        onDeletePersona={onDeletePersona}
        recipes={workspace.recipes || []}
        onCreateRecipe={onCreateRecipe}
        onUpdateRecipe={onUpdateRecipe}
        onDeleteRecipe={onDeleteRecipe}
      />
    </div>
  )
}
