import React, { useCallback, useEffect, useState } from 'react'
import {
  dispatchTask,
  getApproval,
  getHealth,
  getLedger,
  getSafety,
  resetLedger,
  setApproval,
  setSafety,
} from './api.js'
import TaskConsole from './components/TaskConsole.jsx'
import SwarmFeed from './components/SwarmFeed.jsx'
import ChainAuditor from './components/ChainAuditor.jsx'
import SafetyControl from './components/SafetyControl.jsx'
import ApprovalControl from './components/ApprovalControl.jsx'
import AgentsPanel from './components/AgentsPanel.jsx'
import MemoryPanel from './components/MemoryPanel.jsx'
import SkillLibrary from './components/SkillLibrary.jsx'
import EvalDashboard from './components/EvalDashboard.jsx'
import MetricsPanel from './components/MetricsPanel.jsx'

const TABS = [
  { key: 'feed', label: '⌁ Swarm Feed' },
  { key: 'skills', label: '⚒ Skills' },
  { key: 'eval', label: '📊 Eval' },
  { key: 'metrics', label: '📈 Metrics' },
  { key: 'memory', label: '⛁ Memory' },
  { key: 'roster', label: '✦ Roster' },
]

export default function App() {
  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [safety, setSafetyMode] = useState('live')
  const [approval, setApprovalMode] = useState('auto')
  const [tab, setTab] = useState('feed')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [l, h, s, a] = [await getLedger(), await getHealth(), await getSafety(), await getApproval()]
      setLedger(l)
      setHealth(h)
      setSafetyMode(s.mode)
      setApprovalMode(a.mode)
      setError(null)
    } catch {
      setError('Backend unreachable. Start it:  PYTHONPATH=src uvicorn core.api:app --port 8000')
    }
  }, [])

  useEffect(() => {
    refresh()
    // light poll keeps the dashboard live and self-heals a stale error banner
    // (e.g. after a backend restart) without a manual reload.
    const id = setInterval(refresh, 4000)
    return () => clearInterval(id)
  }, [refresh])

  const onDispatch = async (directive, budget) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await dispatchTask(directive, budget)
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

  const onApproval = async (mode) => {
    try {
      const r = await setApproval(mode)
      setApprovalMode(r.mode)
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
        <div className="flex items-center gap-4 flex-wrap">
          <SafetyControl mode={safety} onChange={onSafety} />
          <ApprovalControl mode={approval} onChange={onApproval} />
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
          {result.cost && Object.keys(result.cost).length > 0 && (
            <div className="flex gap-4 text-xs mt-2 text-slate-400">
              <span>⛂ {result.cost.llm_calls} LLM calls</span>
              <span>{result.cost.total_tokens.toLocaleString()} tokens</span>
              <span>~${result.cost.usd.toFixed(4)}</span>
            </div>
          )}
          {result.budget_halt && (
            <div className="mt-2 text-xs text-amber-300 border border-amber-500/40 bg-amber-500/10 rounded px-2 py-1">
              ⛔ budget guard: {result.budget_halt}
            </div>
          )}
          {result.synthesized && result.synthesized.length > 0 && (
            <div className="mt-2 text-xs text-violet-300 border border-violet-500/40 bg-violet-500/10 rounded px-2 py-1">
              ⚗ synthesized:{' '}
              {result.synthesized
                .map((s) => (s.ok ? `${s.name} (${s.status.replace('_', ' ')})` : `rejected (${s.reason})`))
                .join(', ')}
            </div>
          )}
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
          {tab === 'skills' && <SkillLibrary />}
          {tab === 'eval' && <EvalDashboard />}
          {tab === 'metrics' && <MetricsPanel />}
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
