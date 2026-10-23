import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MessageSquarePlus, MessageSquare, MessagesSquare, ShieldCheck, Library, Activity, Settings as SettingsIcon,
  Palette, PanelLeft, Loader2, Keyboard, Download, Copy, Mic, Cpu, Share, AlertTriangle, MailWarning,
} from 'lucide-react'
import { exportConversation, conversationToMarkdown } from './lib/export.js'
import {
  getHealth, getLedger, getAgents, getSafety, setSafety, getApproval, setApproval,
  getAuth, dispatchTask, stopTask, getWorkspace, getSession, createSession, activateSession,
  updateSession, deleteSession, pinSession, createProject, updateProject, deleteProject,
  createPersona, updatePersona, deletePersona,
  createRecipe, updateRecipe, deleteRecipe, searchConversations,
  getAuthState, updateProfile, changePassword, logoutEverywhere, deleteAccount,
  getToken, setToken, clearToken, verifyEmail, resendVerification,
} from './api.js'
import TopBar from './components/TopBar.jsx'
import Sidebar, { THEMES } from './components/Sidebar.jsx'
import RunView from './components/RunView.jsx'
import ProofPage from './components/pages/ProofPage.jsx'
import LibraryPage, { LIBRARY_TABS } from './components/pages/LibraryPage.jsx'
import InsightsPage, { INSIGHTS_TABS } from './components/pages/InsightsPage.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import AuthScreen from './components/AuthScreen.jsx'
import ShortcutsHelp from './components/ShortcutsHelp.jsx'
import Messaging from './components/Messaging.jsx'
import VoiceWake from './components/VoiceWake.jsx'
import { Menu, MenuItem } from './components/ui/Menu.jsx'
import { recognitionSupported } from './lib/speech.js'
import { BRAND, CLI } from './lib/brand.js'

// Top-level views live in the URL hash (#/proof, #/library/tools) so every page
// is linkable and the back button works.
const VIEWS = ['chats', 'proof', 'library', 'insights']
const readRoute = () => {
  const [view, sub] = window.location.hash.replace(/^#\/?/, '').split('/')
  return VIEWS.includes(view) ? { view, sub: sub || '' } : { view: 'chats', sub: '' }
}
const cap = (s) => s[0].toUpperCase() + s.slice(1)

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
    const n = new Notification(r?.success ? `${BRAND} finished` : `${BRAND} stopped`, { body })
    n.onclick = () => { window.focus(); n.close() }
  } catch { /* ignore */ }
}

function Banner({ tone, icon: Icon, children }) {
  const cls = tone === 'bad' ? 'border-bad/30 bg-bad/[0.07] text-bad' : 'border-warn/30 bg-warn/[0.07] text-warn'
  return (
    <div role={tone === 'bad' ? 'alert' : 'status'} className={`mx-auto mt-3 w-[calc(100%-2.5rem)] max-w-5xl flex items-center gap-2 rounded-lg border px-3 py-2 text-[12.5px] ${cls}`}>
      <Icon className="w-4 h-4 shrink-0" /><div className="min-w-0 flex-1 flex flex-wrap items-center gap-x-2">{children}</div>
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('athena-theme') || 'dark')
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('athena-sidebar') === 'collapsed')
  const [route, setRoute] = useState(readRoute)
  const [mobileNav, setMobileNav] = useState(false)
  const [proofFocus, setProofFocus] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState('general')
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

  useEffect(() => {
    const onHash = () => setRoute(readRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const navigate = (view, sub = '') => { window.location.hash = `/${view}${sub ? `/${sub}` : ''}` }
  const { view } = route
  const libTab = LIBRARY_TABS.some((t) => t.key === route.sub) ? route.sub : 'skills'
  const insTab = INSIGHTS_TABS.some((t) => t.key === route.sub) ? route.sub : 'usage'

  useEffect(() => {
    const where = view === 'chats' ? (activeSession?.title || 'New chat') : cap(view)
    document.title = `${where} · ${BRAND}`
  }, [view, activeSession?.title])

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
        try { const r = await verifyEmail(verifyParam); setUser((u) => (u ? r.user : u)); setVerifyMsg('Email verified') }
        catch { /* invalid/expired link */ }
      }
      setAuthReady(true)
    })()
  }, [])

  const onResendVerification = async () => {
    try {
      const out = await resendVerification()
      if (out.dev_link) { window.location.href = out.dev_link; return }  // dev mode: link verifies on reload
      setVerifyMsg('Sent. Check your inbox.')
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
  const openSettings = (tab = 'general') => { setSettingsTab(tab); setSettingsOpen(true) }
  const openProof = (indexes) => { setProofFocus(indexes?.length ? indexes : null); navigate('proof') }

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

  const toggleCollapse = () => setCollapsed((c) => {
    localStorage.setItem('athena-sidebar', c ? 'expanded' : 'collapsed')
    return !c
  })

  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.isContentEditable
      const mod = e.metaKey || e.ctrlKey
      const k = e.key.toLowerCase()
      if (mod && k === 'k') { e.preventDefault(); setPaletteOpen((o) => !o) }
      else if (mod && k === 'b') { e.preventDefault(); toggleCollapse() }
      else if (mod && k === ',') { e.preventDefault(); openSettings('general') }
      else if (e.key === '?' && !typing) { e.preventDefault(); setHelpOpen((o) => !o) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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
      setError(`Can’t reach the server. Start it with:  ${CLI} up`)
    }
  }, [])

  const loadWorkspace = useCallback(async () => {
    try { const w = await getWorkspace(); setWorkspace(w); return w } catch { return null }
    finally { setWsLoading(false) }
  }, [])

  const loadSession = useCallback(async (id) => {
    if (!id) return
    try { const { session } = await getSession(id); setActiveSession(session) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!user) return undefined
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
    if (!user) return undefined
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
      setError(`That task didn’t go through: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  const onStop = async () => { try { await stopTask() } catch { /* ignore */ } }

  const selectSession = async (id) => {
    navigate('chats')
    if (id === workspace.active_id) return
    clearLive()
    try { await activateSession(id) } catch { /* ignore */ }
    await loadSession(id)
    await loadWorkspace()
  }
  const selectRef = useRef(selectSession)
  selectRef.current = selectSession

  const newSession = async (projectId) => {
    navigate('chats')
    // Already on a blank chat in the same place: reuse it rather than piling up empty ones.
    const blank = activeSession && !activeSession.runs?.length && !running && !result
    if (blank && (activeSession.project_id || null) === (projectId || null)) return
    clearLive()
    try { const { session } = await createSession(null, projectId); await loadSession(session.id) } catch { /* ignore */ }
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
  const onRenameSession = async (id, title) => { try { await updateSession(id, { title }) } catch { /* ignore */ }; await loadWorkspace(); if (id === activeSession?.id) loadSession(id) }
  const onDeleteSession = async (id) => {
    try {
      const res = await deleteSession(id)
      setWorkspace(res)
      if (id === activeSession?.id) { clearLive(); await loadSession(res.active_id) }
    } catch { /* ignore */ }
  }
  const onNewProject = async (name) => { try { await createProject(name) } catch { /* ignore */ }; await loadWorkspace() }
  const onUpdateProject = async (id, patch) => { try { await updateProject(id, patch) } catch { /* ignore */ }; await loadWorkspace() }
  const onDeleteProject = async (id) => { try { const res = await deleteProject(id); setWorkspace(res) } catch { /* ignore */ } }
  const onMoveSession = async (id, projectId) => {
    try { await updateSession(id, { project_id: projectId }) } catch { /* ignore */ }
    await loadWorkspace()
    if (id === activeSession?.id) loadSession(id)
  }

  const onSafety = async (mode) => { try { setSafetyMode((await setSafety(mode)).mode) } catch { /* ignore */ } }
  const onApproval = async (mode) => { try { setApprovalMode((await setApproval(mode)).mode) } catch { /* ignore */ } }

  const verification = result?.verification || ledger.verification
  const hasRuns = activeSession?.runs?.length > 0

  const commands = useMemo(() => [
    { id: 'new', section: 'Actions', label: 'New chat', icon: MessageSquarePlus, run: () => newSession(), keywords: 'conversation start' },
    { id: 'settings', section: 'Actions', label: 'Settings', icon: SettingsIcon, hint: '⌘,', run: () => openSettings('general'), keywords: 'account profile password' },
    { id: 'model', section: 'Actions', label: 'Change model', icon: Cpu, run: () => openSettings('model'), keywords: 'llm provider ollama openai anthropic key connect' },
    { id: 'shortcuts', section: 'Actions', label: 'Keyboard shortcuts', icon: Keyboard, hint: '?', run: () => setHelpOpen(true), keywords: 'keys hotkeys' },
    { id: 'sidebar', section: 'Actions', label: collapsed ? 'Expand sidebar' : 'Collapse sidebar', icon: PanelLeft, hint: '⌘B', run: toggleCollapse },
    ...(recognitionSupported() ? [{ id: 'wake', section: 'Actions', label: wakeOn ? 'Turn off hands-free voice' : 'Turn on hands-free voice', icon: Mic, run: () => setWakeOn((v) => !v), keywords: 'voice wake word dictation microphone' }] : []),
    ...(user?.is_admin ? [{ id: 'messaging', section: 'Actions', label: 'Messaging gateways', icon: MessageSquare, run: () => setMessagingOpen(true), keywords: 'telegram discord slack whatsapp channels bot' }] : []),
    ...(hasRuns ? [
      { id: 'export', section: 'Actions', label: 'Download conversation as Markdown', icon: Download, run: () => exportConversation(activeSession), keywords: 'export save share md file' },
      { id: 'copy-convo', section: 'Actions', label: 'Copy conversation as Markdown', icon: Copy, run: () => navigator.clipboard?.writeText(conversationToMarkdown(activeSession)), keywords: 'clipboard share' },
    ] : []),
    { id: 'go-chats', section: 'Go to', label: 'Chats', icon: MessagesSquare, run: () => navigate('chats') },
    { id: 'go-proof', section: 'Go to', label: 'Proof', icon: ShieldCheck, run: () => openProof(null), keywords: 'ledger chain verify signed blocks audit export' },
    ...LIBRARY_TABS.map((t) => ({ id: `lib-${t.key}`, section: 'Go to', label: `Library · ${t.label}`, icon: Library, run: () => navigate('library', t.key), keywords: 'library' })),
    ...INSIGHTS_TABS.map((t) => ({ id: `ins-${t.key}`, section: 'Go to', label: `Insights · ${t.label}`, icon: Activity, run: () => navigate('insights', t.key), keywords: 'insights metrics cost tokens' })),
    ...THEMES.map((t) => ({ id: `theme-${t}`, section: 'Theme', label: `${cap(t)} theme`, icon: Palette, hint: theme === t ? 'current' : '', run: () => applyTheme(t), keywords: 'appearance color' })),
    ...(workspace.sessions || []).map((s) => ({ id: `sess-${s.id}`, sessionId: s.id, section: 'Conversations', label: s.title, icon: MessageSquare, hint: s.id === workspace.active_id ? 'current' : '', run: () => selectRef.current(s.id), keywords: 'chat' })),
  ], [workspace, collapsed, user, activeSession, hasRuns, wakeOn, theme]) // eslint-disable-line react-hooks/exhaustive-deps

  const searchContent = useCallback(async (q) => {
    const { results = [] } = await searchConversations(q)
    return results.map((r) => ({
      id: `hit-${r.id}`, sessionId: r.id, section: 'Matching conversations', label: r.title,
      snippet: r.match === 'content' ? r.snippet : '', icon: MessageSquare, run: () => selectRef.current(r.id),
    }))
  }, [])

  if (!authReady) {
    return <div className="min-h-screen grid place-items-center"><Loader2 className="w-5 h-5 animate-spin text-faint" aria-label="Loading" /></div>
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
        view={view}
        onNavigate={(k) => (k === 'proof' ? openProof(null) : navigate(k))}
        ledger={ledger}
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
        user={user}
        theme={theme}
        onSetTheme={applyTheme}
        onOpenSettings={openSettings}
        onOpenPalette={() => setPaletteOpen(true)}
        onOpenShortcuts={() => setHelpOpen(true)}
        onSignOut={onSignOut}
        mobileOpen={mobileNav}
        onCloseMobile={() => setMobileNav(false)}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <TopBar title={view === 'chats' ? (activeSession?.title || 'New chat') : null} onOpenMobileNav={() => setMobileNav(true)}>
          {view === 'chats' && recognitionSupported() && (
            <button onClick={() => setWakeOn((v) => !v)} aria-pressed={wakeOn}
              className={`btn-ghost p-1.5 relative ${wakeOn ? '!text-accent' : ''}`}
              aria-label={wakeOn ? 'Turn off hands-free voice' : 'Turn on hands-free voice'}
              title={wakeOn ? 'Hands-free voice is on' : 'Hands-free voice'}>
              <Mic className="w-4 h-4" />
              {wakeOn && <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />}
            </button>
          )}
          {view === 'chats' && hasRuns && (
            <Menu align="end" width="w-56"
              trigger={(t) => (
                <button {...t} className="btn-ghost p-1.5" aria-label="Export conversation" title="Export">
                  <Share className="w-4 h-4" />
                </button>
              )}>
              <MenuItem icon={Copy} onSelect={() => navigator.clipboard?.writeText(conversationToMarkdown(activeSession))}>Copy as Markdown</MenuItem>
              <MenuItem icon={Download} onSelect={() => exportConversation(activeSession)}>Download Markdown</MenuItem>
            </Menu>
          )}
        </TopBar>

        <main className="flex-1 flex flex-col">
          {error && <Banner tone="bad" icon={AlertTriangle}><span>{error}</span></Banner>}
          {!user.email_verified && (
            <Banner tone="warn" icon={MailWarning}>
              <span>Verify your email to secure your account. We sent a link to {user.email}.</span>
              <button onClick={onResendVerification} className="underline underline-offset-2">Resend</button>
              {verifyMsg && <span className="text-ok">{verifyMsg}</span>}
            </Banner>
          )}

          {view === 'chats' && (
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
              demo={health ? !health.live : false}
              onOpenModel={() => openSettings('model')}
              onOpenProof={openProof}
              model={{ current: health?.llm, live: health?.live, onChanged: refresh, onOpenModel: () => openSettings('model') }}
              persona={{
                personas: workspace.personas || [],
                activeId: activeSession?.persona_id,
                onPick: onSetSessionPersona,
                onManage: () => navigate('library', 'personas'),
              }}
            />
          )}
          {view === 'proof' && (
            <ProofPage ledger={ledger} roleOf={roleOf} agentsMap={agentsMap} onVerify={refresh}
              focus={proofFocus} onClearFocus={() => setProofFocus(null)} />
          )}
          {view === 'library' && (
            <LibraryPage
              tab={libTab} onTab={(t) => navigate('library', t)} user={user} onRefresh={refresh}
              personas={workspace.personas || []} onCreatePersona={onCreatePersona} onUpdatePersona={onUpdatePersona} onDeletePersona={onDeletePersona}
              recipes={workspace.recipes || []} onCreateRecipe={onCreateRecipe} onUpdateRecipe={onUpdateRecipe} onDeleteRecipe={onDeleteRecipe}
            />
          )}
          {view === 'insights' && <InsightsPage tab={insTab} onTab={(t) => navigate('insights', t)} onRefresh={refresh} />}
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} search={searchContent} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <Messaging open={messagingOpen} onClose={() => setMessagingOpen(false)} />
      <VoiceWake enabled={wakeOn} running={running} result={result} onDispatch={onDispatch} onDisable={() => setWakeOn(false)} />
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
        onOpenMessaging={() => setMessagingOpen(true)}
      />
    </div>
  )
}
