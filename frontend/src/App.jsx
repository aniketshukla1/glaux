import React, { useCallback, useEffect, useState } from 'react'
import {
  dispatchTask,
  getHealth,
  getLedger,
  getSafety,
  resetLedger,
  setSafety,
} from './api.js'
import TaskConsole from './components/TaskConsole.jsx'
import SwarmFeed from './components/SwarmFeed.jsx'
import ChainAuditor from './components/ChainAuditor.jsx'
import SafetyControl from './components/SafetyControl.jsx'
import AgentsPanel from './components/AgentsPanel.jsx'
import MemoryPanel from './components/MemoryPanel.jsx'

const TABS = [
  { key: 'feed', label: '⌁ Swarm Feed' },
  { key: 'memory', label: '⛁ Memory' },
  { key: 'roster', label: '✦ Roster' },
]

export default function App() {
  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [safety, setSafetyMode] = useState('live')
  const [tab, setTab] = useState('feed')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [l, h, s] = [await getLedger(), await getHealth(), await getSafety()]
      setLedger(l)
      setHealth(h)
      setSafetyMode(s.mode)
      setError(null)
    } catch {
      setError('Backend unreachable. Start it:  PYTHONPATH=src uvicorn core.api:app --port 8000')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const onDispatch = async (directive) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await dispatchTask(directive)
      setResult(r)
      setTab('feed')
      await refresh()
    } catch (e) {
      setError(`Dispatch failed: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const onReset = async () => {
    try {
      await resetLedger()
      setResult(null)
      await refresh()
    } catch {
      /* ignore */
    }
  }

  const onSafety = async (mode) => {
    try {
      const r = await setSafety(mode)
      setSafetyMode(r.mode)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="min-h-screen p-6 max-w-7xl mx-auto">
      <header className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">
            Athena <span className="text-athena-accent">·</span>{' '}
            <span className="text-slate-400 font-normal">Swarm Console</span>
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Signed, sandboxed, self-improving multi-agent swarm
          </p>
        </div>
        <div className="flex items-center gap-4">
          <SafetyControl mode={safety} onChange={onSafety} />
          {health && (
            <span
              className={`px-2 py-1 rounded text-xs ${
                health.live
                  ? 'bg-athena-accent/15 text-athena-accent'
                  : 'bg-slate-600/20 text-slate-400'
              }`}
            >
              {health.live ? '● live' : '○ demo'} · {health.llm}
            </span>
          )}
        </div>
      </header>

      {error && (
        <div className="glass p-3 mb-4 border-rose-500/40 text-rose-300 text-sm">{error}</div>
      )}

      <TaskConsole onDispatch={onDispatch} loading={loading} onReset={onReset} />

      {result && (
        <div className="glass p-4 mt-4">
          <div className="flex items-center gap-3 mb-2 flex-wrap">
            <span
              className={`px-2 py-0.5 rounded text-xs font-semibold ${
                result.success
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-rose-500/15 text-rose-300'
              }`}
            >
              {result.success ? 'SUCCESS' : 'INCOMPLETE'}
            </span>
            <span className="text-sm text-slate-300">{result.final}</span>
          </div>
          <div className="text-xs text-slate-500">
            plan: {result.plan.map((s) => `${s.id}:${s.role}`).join(' → ')} ·{' '}
            {result.new_blocks.length} new signed blocks
          </div>
        </div>
      )}

      <div className="flex gap-1 mt-6 mb-4">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm border transition ${
              tab === t.key
                ? 'text-slate-100 border-slate-500/50 bg-slate-700/30'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {tab === 'feed' && <SwarmFeed blocks={ledger.blocks} />}
          {tab === 'memory' && <MemoryPanel />}
          {tab === 'roster' && <AgentsPanel />}
        </div>
        <div>
          <ChainAuditor ledger={ledger} onVerify={refresh} />
        </div>
      </div>
    </div>
  )
}
