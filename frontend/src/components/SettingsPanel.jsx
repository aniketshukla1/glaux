import React, { useState } from 'react'
import { Settings, Palette, ShieldHalf, Cpu, Lock, Check } from 'lucide-react'
import Drawer from './Drawer.jsx'
import LlmControl from './LlmControl.jsx'
import SafetyControl from './SafetyControl.jsx'
import ApprovalControl from './ApprovalControl.jsx'

const THEMES = [
  { key: 'dark', label: 'Dark', bg: '#090b10', surface: '#11151e', accent: '#2dd4bf', fg: '#e2e8f0' },
  { key: 'light', label: 'Light', bg: '#fafaf9', surface: '#ffffff', accent: '#0d9488', fg: '#0f172a' },
  { key: 'oled', label: 'OLED', bg: '#000000', surface: '#0c0c0e', accent: '#2dd4bf', fg: '#ededf0' },
  { key: 'midnight', label: 'Midnight', bg: '#080c1c', surface: '#10162c', accent: '#38bdf8', fg: '#e0e7f5' },
  { key: 'nord', label: 'Nord', bg: '#2e3440', surface: '#3b4252', accent: '#88c0d0', fg: '#d8dee9' },
  { key: 'ember', label: 'Ember', bg: '#18100e', surface: '#261a16', accent: '#fb923c', fg: '#f5ece6' },
]

const TABS = [
  { key: 'appearance', label: 'Appearance', Icon: Palette },
  { key: 'model', label: 'Model', Icon: Cpu },
  { key: 'safety', label: 'Safety', Icon: ShieldHalf },
  { key: 'security', label: 'Security', Icon: Lock },
]

function ThemeSwatch({ t, active, onPick }) {
  return (
    <button onClick={() => onPick(t.key)}
      className={`relative rounded-xl overflow-hidden border text-left transition ${active ? 'border-accent ring-1 ring-accent/40' : 'border-line/15 hover:border-line/30'}`}
      style={{ background: t.bg }}>
      <div className="p-2.5 h-16 flex flex-col justify-between">
        <div className="flex gap-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: t.accent }} />
          <span className="h-2.5 flex-1 rounded-full" style={{ background: t.surface }} />
        </div>
        <div className="space-y-1">
          <span className="block h-1.5 w-3/4 rounded-full" style={{ background: t.surface }} />
          <span className="block h-1.5 w-1/2 rounded-full" style={{ background: t.accent, opacity: 0.7 }} />
        </div>
      </div>
      <div className="px-2.5 py-1.5 flex items-center gap-1.5 text-xs" style={{ background: t.surface, color: t.fg }}>
        {active && <Check className="w-3 h-3" style={{ color: t.accent }} />}
        {t.label}
      </div>
    </button>
  )
}

function Field({ title, hint, children }) {
  return (
    <div className="mb-5">
      <div className="text-fg text-sm font-medium">{title}</div>
      {hint && <p className="text-faint text-xs mt-0.5 mb-2.5">{hint}</p>}
      {!hint && <div className="mb-2" />}
      {children}
    </div>
  )
}

export default function SettingsPanel({
  open, onClose, theme, onSetTheme, safety, onSafety, approval, onApproval, auth,
}) {
  const [tab, setTab] = useState('appearance')
  return (
    <Drawer open={open} onClose={onClose} title="Settings" icon={<Settings className="w-4 h-4 text-muted" />} width={440}>
      <div className="flex gap-1 flex-wrap mb-5">
        {TABS.map(({ key, label, Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm border transition ${
              tab === key ? 'text-fg border-line/30 bg-line/8' : 'text-faint border-transparent hover:text-muted'
            }`}>
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>

      {tab === 'appearance' && (
        <Field title="Theme" hint="Pick a look — the whole app follows it.">
          <div className="grid grid-cols-3 gap-2">
            {THEMES.map((t) => <ThemeSwatch key={t.key} t={t} active={theme === t.key} onPick={onSetTheme} />)}
          </div>
        </Field>
      )}

      {tab === 'model' && (
        <Field title="Model" hint="Run the swarm on any of 30+ providers — OpenAI, Gemini, Grok, DeepSeek, Mistral, Sarvam, Groq, OpenRouter, local models, or the offline demo.">
          <LlmControl />
        </Field>
      )}

      {tab === 'safety' && (
        <>
          <Field title="Kill switch" hint="Halted stops all execution; dry-run skips side effects.">
            <SafetyControl mode={safety} onChange={onSafety} />
          </Field>
          <Field title="Approval" hint="In gated mode, skills the swarm writes need your approval before they can run.">
            <ApprovalControl mode={approval} onChange={onApproval} />
          </Field>
        </>
      )}

      {tab === 'security' && (
        <Field title="API security" hint="How the backend authenticates requests.">
          <div className="text-xs text-muted leading-relaxed">
            {auth?.enabled
              ? 'HMAC request signing is enabled — every request is verified.'
              : 'Open (no auth). Set ATHENA_API_SECRET to require signed requests.'}
          </div>
        </Field>
      )}
    </Drawer>
  )
}
