import React from 'react'
import Page from './Page.jsx'
import MetricsPanel from '../MetricsPanel.jsx'
import EvalDashboard from '../EvalDashboard.jsx'
import { EvolutionTab } from '../SettingsPanel.jsx'

export const INSIGHTS_TABS = [
  { key: 'usage', label: 'Usage', hint: 'Tasks, model calls, tokens and spend since the server started.' },
  { key: 'evolution', label: 'Self-improvement', hint: 'How the swarm tunes itself from outcomes. Every change is tested against past runs, signed to the chain, and can be undone.' },
  { key: 'benchmarks', label: 'Benchmarks', hint: 'Score the skill library against a fixed suite to see whether changes helped.' },
]

export default function InsightsPage({ tab, onTab, onRefresh }) {
  return (
    <Page title="Insights" tabs={INSIGHTS_TABS} tab={tab} onTab={onTab}
      description="What the swarm costs, how well it performs, and how it is improving itself.">
      {tab === 'usage' && <MetricsPanel />}
      {tab === 'evolution' && <EvolutionTab onRefresh={onRefresh} />}
      {tab === 'benchmarks' && <EvalDashboard />}
    </Page>
  )
}
