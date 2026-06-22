import React, { useState } from 'react'
import { Hammer, Plug, BarChart3, Activity, Database, Users, Link2, LayoutGrid, CalendarClock, UsersRound, MessageSquare, X } from 'lucide-react'
import Modal from './Modal.jsx'
import SkillLibrary from './SkillLibrary.jsx'
import McpPanel from './McpPanel.jsx'
import SchedulePanel from './SchedulePanel.jsx'
import EvalDashboard from './EvalDashboard.jsx'
import MetricsPanel from './MetricsPanel.jsx'
import MemoryPanel from './MemoryPanel.jsx'
import AgentsPanel from './AgentsPanel.jsx'
import ChainAuditor from './ChainAuditor.jsx'
import SwarmFeed from './SwarmFeed.jsx'
import AdminPanel from './AdminPanel.jsx'

const TABS = [
  { key: 'skills', label: 'Skills', Icon: Hammer },
  { key: 'mcp', label: 'Tools', Icon: Plug },
  { key: 'schedules', label: 'Schedules', Icon: CalendarClock },
  { key: 'eval', label: 'Eval', Icon: BarChart3 },
  { key: 'metrics', label: 'Metrics', Icon: Activity },
  { key: 'memory', label: 'Memory', Icon: Database },
  { key: 'roster', label: 'Agents', Icon: Users },
  { key: 'ledger', label: 'Ledger', Icon: Link2 },
]

export default function Studio({ open, onClose, ledger, blocks, onVerify, user, onOpenMessaging }) {
  const [tab, setTab] = useState('skills')
  const tabs = user?.is_admin
    ? [...TABS, { key: 'messaging', label: 'Messaging', Icon: MessageSquare }, { key: 'team', label: 'Team', Icon: UsersRound }]
    : TABS
  const onTab = (key) => {
    if (key === 'messaging') { onClose(); onOpenMessaging?.() }  // opens its own full-screen modal
    else setTab(key)
  }
  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-line/10 shrink-0">
        <LayoutGrid className="w-4 h-4 text-muted" />
        <h2 className="text-fg font-medium">Studio</h2>
        <button onClick={onClose} className="btn p-1.5 ml-auto" aria-label="Close"><X className="w-4 h-4" /></button>
      </div>

      <div className="flex flex-1 min-h-0">
        <nav className="w-48 sm:w-52 shrink-0 border-r border-line/10 p-3 space-y-0.5 overflow-y-auto">
          {tabs.map(({ key, label, Icon }) => (
            <button key={key} onClick={() => onTab(key)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition ${
                tab === key ? 'text-fg bg-line/10 font-medium' : 'text-muted hover:text-fg hover:bg-line/5'
              }`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 sm:px-8 py-7">
            {tab === 'skills' && <SkillLibrary />}
            {tab === 'mcp' && <McpPanel />}
            {tab === 'schedules' && <SchedulePanel />}
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
            {tab === 'team' && user?.is_admin && <AdminPanel currentUserId={user.id} />}
          </div>
        </div>
      </div>
    </Modal>
  )
}
