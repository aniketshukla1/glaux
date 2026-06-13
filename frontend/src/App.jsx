import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getHealth, getLedger, getAgents, getSafety, setSafety, getApproval, setApproval,
  getAuth, dispatchTask,
} from './api.js'
import TopBar from './components/TopBar.jsx'
import RunView from './components/RunView.jsx'
import Studio from './components/Studio.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'

const mergeBlocks = (a, b) => {
  const seen = new Set(a.map((x) => x.index))
  const merged = [...a, ...b.filter((x) => !seen.has(x.index))]
  return merged.sort((x, y) => x.index - y.index)
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('athena-theme') || 'dark')
  const [studioOpen, setStudioOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [agentsMap, setAgentsMap] = useState({})
  const [safety, setSafetyMode] = useState('live')
  const [approval, setApprovalMode] = useState('auto')
  const [auth, setAuth] = useState({ enabled: false })
  const [error, setError] = useState(null)

  const [liveBlocks, setLiveBlocks] = useState([])
  const [goal, setGoal] = useState(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('athena-theme', theme)
  }, [theme])

  const refresh = useCallback(async () => {
    try {
      const [l, h, a, s, ap, au] = [
        await getLedger(), await getHealth(), await getAgents(),
        await getSafety(), await getApproval(), await getAuth(),
      ]
      setLedger(l)
      setHealth(h)
      setAgentsMap(Object.fromEntries(a.agents.map((x) => [x.agent_id, x.role])))
      setSafetyMode(s.mode)
      setApprovalMode(ap.mode)
      setAuth(au)
      setError(null)
    } catch {
      setError('Backend unreachable — start it: PYTHONPATH=src uvicorn core.api:app --port 8000')
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh])

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

  const onDispatch = async (directive) => {
    setGoal(directive)
    setRunning(true)
    setResult(null)
    setLiveBlocks([])
    try {
      const r = await dispatchTask(directive)
      setResult(r)
      setLiveBlocks((prev) => mergeBlocks(prev, r.new_blocks || []))
      await refresh()
    } catch (e) {
      setError(`Dispatch failed: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  const onReset = () => { setGoal(null); setResult(null); setLiveBlocks([]) }

  const onSafety = async (mode) => { try { setSafetyMode((await setSafety(mode)).mode) } catch {} }
  const onApproval = async (mode) => { try { setApprovalMode((await setApproval(mode)).mode) } catch {} }

  const verification = result?.verification || ledger.verification

  return (
    <div className="min-h-screen px-5 sm:px-8 max-w-5xl mx-auto">
      <TopBar
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
        onOpenStudio={() => setStudioOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        verified={ledger.verification ? ledger.verification.valid : null}
        health={health}
      />

      {error && (
        <div className="glass p-3 mb-4 text-sm" style={{ borderColor: 'rgb(244 63 94 / 0.4)', color: 'rgb(251 113 133)' }}>
          {error}
        </div>
      )}

      <main className="pt-2">
        <RunView
          blocks={liveBlocks}
          roleOf={roleOf}
          running={running}
          result={result}
          goal={goal}
          onDispatch={onDispatch}
          onReset={onReset}
          verification={verification}
        />
      </main>

      <Studio
        open={studioOpen}
        onClose={() => setStudioOpen(false)}
        ledger={ledger}
        blocks={liveBlocks}
        onVerify={refresh}
      />
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        onSetTheme={setTheme}
        safety={safety}
        onSafety={onSafety}
        approval={approval}
        onApproval={onApproval}
        auth={auth}
      />
    </div>
  )
}
