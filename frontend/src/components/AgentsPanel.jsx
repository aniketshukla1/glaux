import React, { useEffect, useState } from 'react'
import { getAgents } from '../api.js'

const ROLE_COLOR = {
  router: '#818cf8',
  coder: '#f472b6',
  researcher: '#22d3ee',
  reflector: '#a78bfa',
}
const short = (s) => (s ? `${s.slice(0, 10)}…${s.slice(-6)}` : '')

export default function AgentsPanel() {
  const [agents, setAgents] = useState([])

  useEffect(() => {
    getAgents()
      .then((d) => setAgents(d.agents))
      .catch(() => {})
  }, [])

  return (
    <section>
      <h2 className="text-slate-300 mb-3 flex items-center gap-2">
        ✦ Agent Roster <span className="text-xs text-slate-500">({agents.length})</span>
      </h2>
      <div className="space-y-2">
        {agents.map((a) => {
          const color = ROLE_COLOR[a.role] || '#94a3b8'
          return (
            <div key={a.role} className="glass p-3 flex items-center gap-3">
              <span
                className="px-2 py-0.5 rounded text-xs font-semibold w-24 text-center shrink-0"
                style={{ background: `${color}22`, color }}
              >
                {a.role}
              </span>
              <div className="min-w-0">
                <div className="hash" title={a.public_key}>
                  key {short(a.public_key)}
                </div>
                <div className="text-xs text-slate-500">namespace: {a.namespace}</div>
              </div>
            </div>
          )
        })}
        {agents.length === 0 && (
          <div className="glass p-6 text-center text-slate-500 text-sm">No agents.</div>
        )}
      </div>
      <p className="text-xs text-slate-500 mt-3 leading-relaxed">
        Each agent is an Ed25519 keypair. Its <code>agent_id</code> is the base58 of its public
        key; every action it signs is verifiable against it.
      </p>
    </section>
  )
}
