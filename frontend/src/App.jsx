import React, { useCallback, useEffect, useState } from 'react'
import { dispatchTask, getHealth, getLedger, resetLedger } from './api.js'
import TaskConsole from './components/TaskConsole.jsx'
import SwarmFeed from './components/SwarmFeed.jsx'
import ChainAuditor from './components/ChainAuditor.jsx'

export default function App() {
  const [health, setHealth] = useState(null)
  const [ledger, setLedger] = useState({ count: 0, blocks: [], verification: null })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [l, h] = [await getLedger(), await getHealth()]
      setLedger(l)
      setHealth(h)
      setError(null)
    } catch {
      setError(
        'Backend unreachable. Start it:  PYTHONPATH=src uvicorn core.api:app --port 8000',
      )
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

  return (
    <div className="min-h-screen p-6 max-w-7xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">
            Athena <span className="text-athena-accent">·</span>{' '}
            <span className="text-slate-400 font-normal">Swarm Console</span>
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Signed, sandboxed, self-improving multi-agent swarm
          </p>
        </div>
        {health && (
          <div className="text-right text-xs">
            <span
              className={`px-2 py-1 rounded ${
                health.live
                  ? 'bg-athena-accent/15 text-athena-accent'
                  : 'bg-slate-600/20 text-slate-400'
              }`}
            >
              {health.live ? '● live' : '○ demo'} · {health.llm}
            </span>
          </div>
        )}
      </header>

      {error && (
        <div className="glass p-3 mb-4 border-rose-500/40 text-rose-300 text-sm">{error}</div>
      )}

      <TaskConsole onDispatch={onDispatch} loading={loading} onReset={onReset} />

      {result && (
        <div className="glass p-4 mt-4">
          <div className="flex items-center gap-3 mb-2">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <div className="lg:col-span-2">
          <SwarmFeed blocks={ledger.blocks} />
        </div>
        <div>
          <ChainAuditor ledger={ledger} onVerify={refresh} />
        </div>
      </div>
    </div>
  )
}
