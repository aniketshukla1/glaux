import { BRAND } from './brand.js'

// Turn the raw signed ledger into a human-readable timeline.
// Power users can still open the underlying blocks (the "proof") on any step.

export const ROLE_META = {
  router: { label: BRAND, sub: 'orchestrator', color: '#818cf8' },
  coder: { label: 'Coder', sub: 'builds & computes', color: '#f472b6' },
  researcher: { label: 'Researcher', sub: 'gathers & explains', color: '#22d3ee' },
  web: { label: 'Web Scout', sub: 'reads & cites the web', color: '#38bdf8' },
  scientist: { label: 'Scientist', sub: 'explains mechanisms', color: '#34d399' },
  analyst: { label: 'Analyst', sub: 'compares & quantifies', color: '#fbbf24' },
  engineer: { label: 'Engineer', sub: 'designs systems', color: '#60a5fa' },
  tester: { label: 'Tester', sub: 'finds the edge cases', color: '#fb7185' },
  writer: { label: 'Writer', sub: 'turns work into prose', color: '#e879f9' },
  reflector: { label: 'Reviewer', sub: 'verifies the work', color: '#a78bfa' },
  agent: { label: 'Agent', sub: '', color: '#94a3b8' },
}

export const short = (s) => (s ? `${s.slice(0, 6)}…${s.slice(-4)}` : '')

// Role hues are fixed identity colours. Mixing them toward the foreground keeps
// icons legible in light themes (they darken) and dark themes (they lighten).
export const roleColor = (role) =>
  `color-mix(in oklab, ${(ROLE_META[role] || ROLE_META.agent).color} 74%, rgb(var(--fg)))`

// One-line summary of a run for the collapsed trace: who worked, how many
// steps, what was learned, how many blocks were signed.
export function summarizeRun(blocks, roleOf) {
  const timeline = buildTimeline(blocks || [], roleOf)
  const steps = timeline.filter((i) => i.kind === 'step' && i.role !== 'router')
  const roles = [...new Set(steps.map((s) => s.role))]
  const learned = steps.map((s) => s.learned).filter(Boolean)
  const tools = steps.reduce((n, s) => n + s.activities.filter((a) => a.icon === 'tool' || a.icon === 'skill').length, 0)
  const revised = steps.some((s) => s.verdict === 'retry')
  return { timeline, steps, roles, learned, tools, revised, signed: (blocks || []).length }
}

function clip(s, n = 90) {
  if (!s) return ''
  s = String(s).replace(/```json[\s\S]*?```/g, '').replace(/\s+/g, ' ').trim()
  return s.length > n ? `${s.slice(0, n)}…` : s
}

// A single visible activity line within a step (tool use / completion). Returns
// null for noise we fold away (raw THINK, intermediate observations).
function describeActivity(b) {
  const p = b.payload || {}
  if (b.action_type === 'MCP_TOOL') {
    const args = p.args && Object.keys(p.args).length ? JSON.stringify(p.args) : ''
    return { icon: 'tool', text: `used the ${p.tool} tool`, detail: args, ok: p.ok !== false }
  }
  if (b.action_type === 'CALL_SKILL') {
    return { icon: 'skill', text: `ran the ${p.skill_id} skill`, detail: '', ok: true }
  }
  if (b.action_type === 'EMIT_OBSERVATION') {
    if (p.finish) return { icon: 'check', text: 'completed its part', detail: clip(p.result), ok: true }
    if (p.aborted) return { icon: 'alert', text: 'stopped', detail: clip(p.reason), ok: false }
    if (p.budget_halt) return { icon: 'alert', text: 'hit the budget limit', detail: clip(p.reason), ok: false }
    return null
  }
  return null
}

// Derive the live swarm graph (agents as nodes, handoffs as edges) from the
// signed blocks — the visual nobody else can show, because nobody else has a
// real signed multi-agent swarm underneath.
export function buildSwarmGraph(blocks, roleOf, { running = false } = {}) {
  const timeline = buildTimeline(blocks, roleOf)
  const steps = timeline.filter((i) => i.kind === 'step')
  const hasReflect = steps.some((s) => s.verdict) || timeline.some((i) => i.kind === 'reflect')
  const lastStep = steps[steps.length - 1]

  const order = []
  const byRole = {}
  for (const s of steps) {
    if (s.role === 'router') continue
    if (!byRole[s.role]) { byRole[s.role] = []; order.push(s.role) }
    byRole[s.role].push(s)
  }

  const statusFor = (role) => {
    const ss = byRole[role]
    if (ss.some((s) => s.verdict === 'retry')) return 'revising'
    if (ss.some((s) => s.verdict && s.verdict !== 'retry')) return 'verified'
    if (running && lastStep && lastStep.role === role && !lastStep.verdict) return 'working'
    return 'done'
  }

  const specialists = order.map((role) => ({ id: role, role, status: statusFor(role) }))
  const anyWorking = specialists.some((s) => s.status === 'working')
  const routerStatus = running && !anyWorking && (!lastStep || !lastStep.verdict) ? 'working' : (specialists.length ? 'done' : (running ? 'working' : 'idle'))

  const nodes = [{ id: 'router', role: 'router', status: routerStatus }, ...specialists]
  if (hasReflect) {
    const reflecting = running && lastStep && lastStep.role && !lastStep.verdict
    nodes.push({ id: 'reflector', role: 'reflector', status: reflecting ? 'idle' : 'verified' })
  }

  const edges = []
  for (const s of specialists) {
    edges.push({ from: 'router', to: s.id, active: s.status === 'working' })
    if (hasReflect && byRole[s.id].some((st) => st.verdict)) {
      edges.push({ from: s.id, to: 'reflector', active: false })
    }
  }
  return { nodes, edges }
}

export function buildTimeline(blocks, roleOf) {
  const items = []
  let step = null

  for (const b of blocks) {
    const t = b.action_type
    if (t === 'PLAN') {
      items.push({ kind: 'plan', steps: b.payload?.plan || [], blocks: [b], index: b.index })
      step = null
    } else if (t === 'CALL_AGENT') {
      step = {
        kind: 'step',
        role: roleOf(b.payload?.target) || 'agent',
        activities: [],
        verdict: null,
        learned: null,
        blocks: [b],
        index: b.index,
      }
      items.push(step)
    } else if (t === 'CAPABILITY_GRANT') {
      if (step) step.blocks.push(b)
    } else if (t === 'REFLECT') {
      if (step) {
        step.verdict = b.payload?.verdict || 'accept'
        step.blocks.push(b)
      } else {
        items.push({ kind: 'reflect', verdict: b.payload?.verdict, blocks: [b], index: b.index })
      }
    } else if (t === 'SYNTHESIZE_SKILL') {
      if (step) {
        if (b.payload?.ok) step.learned = b.payload?.skill
        step.blocks.push(b)
      }
    } else {
      const act = describeActivity(b)
      if (!step) {
        step = { kind: 'step', role: roleOf(b.agent_id) || 'agent', activities: [], verdict: null, learned: null, blocks: [], index: b.index }
        items.push(step)
      }
      step.blocks.push(b)
      if (act) step.activities.push(act)
    }
  }
  return items
}
