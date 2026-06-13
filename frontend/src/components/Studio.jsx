import React, { useState } from 'react'
import { Hammer, Plug, BarChart3, Activity, Database, Users, Link2, LayoutGrid } from 'lucide-react'
import Drawer from './Drawer.jsx'
import SkillLibrary from './SkillLibrary.jsx'
import McpPanel from './McpPanel.jsx'
import EvalDashboard from './EvalDashboard.jsx'
import MetricsPanel from './MetricsPanel.jsx'
import MemoryPanel from './MemoryPanel.jsx'
import AgentsPanel from './AgentsPanel.jsx'
import ChainAuditor from './ChainAuditor.jsx'
import SwarmFeed from './SwarmFeed.jsx'

const TABS = [
  { key: 'skills', label: 'Skills', Icon: Hammer },
  { key: 'mcp', label: 'Tools', Icon: Plug },
  { key: 'eval', label: 'Eval', Icon: BarChart3 },
  { key: 'metrics', label: 'Metrics', Icon: Activity },
  { key: 'memory', label: 'Memory', Icon: Database },
  { key: 'roster', label: 'Agents', Icon: Users },
  { key: 'ledger', label: 'Ledger', Icon: Link2 },
]

export default function Studio({ open, onClose, ledger, blocks, onVerify }) {
  const [tab, setTab] = useState('skills')
  return (
    <Drawer open={open} onClose={onClose} title="Studio" icon={<LayoutGrid className="w-4 h-4 text-muted" />} width={700} dark>
      <div className="flex gap-1 flex-wrap mb-4">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition ${
              tab === key ? 'text-fg border-line/30 bg-line/8' : 'text-faint border-transparent hover:text-muted'
            }`}
          >
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>
      {tab === 'skills' && <SkillLibrary />}
      {tab === 'mcp' && <McpPanel />}
      {tab === 'eval' && <EvalDashboard />}
      {tab === 'metrics' && <MetricsPanel />}
      {tab === 'memory' && <MemoryPanel />}
      {tab === 'roster' && <AgentsPanel />}
      {tab === 'ledger' && (
        <div className="space-y-4">
          <ChainAuditor ledger={ledger} onVerify={onVerify} />
          <SwarmFeed blocks={blocks} />
        </div>
      )}
    </Drawer>
  )
}
