import React from 'react'
import Page from './Page.jsx'
import SkillLibrary from '../SkillLibrary.jsx'
import McpPanel from '../McpPanel.jsx'
import MemoryPanel from '../MemoryPanel.jsx'
import SchedulePanel from '../SchedulePanel.jsx'
import Personas from '../Personas.jsx'
import Recipes from '../Recipes.jsx'
import { PlaybooksTab, SubagentsTab } from '../SettingsPanel.jsx'

export const LIBRARY_TABS = [
  { key: 'skills', label: 'Skills', hint: 'Tools the swarm wrote for itself. New ones start quarantined and run in a sandbox; they’re promoted once they keep working.' },
  { key: 'tools', label: 'Tools', hint: 'Built-in tools plus any MCP servers you connect. The swarm picks from these while it works.' },
  { key: 'memory', label: 'Memory', hint: 'What the swarm remembers: facts, past episodes, and procedures it learned.' },
  { key: 'playbooks', label: 'Playbooks', hint: 'Step-by-step procedures you write. The swarm consults them when a task matches.' },
  { key: 'agents', label: 'Sub-agents', hint: 'Specialists you define. The planner can put them on a team alongside the built-in ones.' },
  { key: 'personas', label: 'Personas', hint: 'Custom assistants with their own instructions. Pick one for any chat from the composer.' },
  { key: 'recipes', label: 'Recipes', hint: 'Saved task templates. Type / in the composer to run one.' },
  { key: 'schedules', label: 'Schedules', hint: 'Tasks that run on their own, on a timetable. Each run is signed like any other.' },
]

export default function LibraryPage({
  tab, onTab, user, onRefresh,
  personas, onCreatePersona, onUpdatePersona, onDeletePersona,
  recipes, onCreateRecipe, onUpdateRecipe, onDeleteRecipe,
}) {
  const tabs = LIBRARY_TABS.map((t) => ({
    ...t, count: t.key === 'personas' ? personas.length : t.key === 'recipes' ? recipes.length : undefined,
  }))
  return (
    <Page title="Library" tabs={tabs} tab={tab} onTab={onTab}
      description="Everything the swarm can draw on: skills it wrote, tools you connected, what it remembers, and the procedures and specialists you defined.">
      {tab === 'skills' && <SkillLibrary />}
      {tab === 'tools' && <McpPanel user={user} />}
      {tab === 'memory' && <MemoryPanel />}
      {tab === 'playbooks' && <PlaybooksTab onRefresh={onRefresh} />}
      {tab === 'agents' && <SubagentsTab />}
      {tab === 'personas' && <Personas personas={personas} onCreate={onCreatePersona} onUpdate={onUpdatePersona} onDelete={onDeletePersona} />}
      {tab === 'recipes' && <Recipes recipes={recipes} onCreate={onCreateRecipe} onUpdate={onUpdateRecipe} onDelete={onDeleteRecipe} />}
      {tab === 'schedules' && <SchedulePanel />}
    </Page>
  )
}
