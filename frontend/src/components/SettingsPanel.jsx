import React from 'react'
import { Settings, Sun, Moon, ShieldHalf, UserCheck, Cpu, Lock } from 'lucide-react'
import Drawer from './Drawer.jsx'
import LlmControl from './LlmControl.jsx'
import SafetyControl from './SafetyControl.jsx'
import ApprovalControl from './ApprovalControl.jsx'

function Section({ icon, title, hint, children }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-fg text-sm font-medium">{title}</span>
      </div>
      {hint && <p className="text-faint text-xs mb-2.5">{hint}</p>}
      {children}
    </div>
  )
}

export default function SettingsPanel({
  open, onClose, theme, onSetTheme, safety, onSafety, approval, onApproval, auth,
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Settings" icon={<Settings className="w-4 h-4 text-muted" />} width={420}>
      <Section icon={<Sun className="w-4 h-4 text-muted" />} title="Appearance">
        <div className="flex gap-2">
          {[
            { key: 'dark', label: 'Dark', Icon: Moon },
            { key: 'light', label: 'Light', Icon: Sun },
          ].map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => onSetTheme(key)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg border text-sm transition ${
                theme === key ? 'border-accent/40 text-accent bg-accent/10' : 'border-line/15 text-muted hover:text-fg'
              }`}
            >
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>
      </Section>

      <Section icon={<Cpu className="w-4 h-4 text-muted" />} title="Model" hint="Run the swarm on any of 30+ providers — OpenAI, Gemini, Grok, DeepSeek, Mistral, Sarvam, Groq, OpenRouter, local models (Ollama / LM Studio / vLLM), or the offline demo.">
        <LlmControl />
      </Section>

      <Section icon={<ShieldHalf className="w-4 h-4 text-muted" />} title="Safety" hint="The kill switch. Halted stops all execution; dry-run skips side effects.">
        <SafetyControl mode={safety} onChange={onSafety} />
      </Section>

      <Section icon={<UserCheck className="w-4 h-4 text-muted" />} title="Approval" hint="In gated mode, skills the swarm writes need your approval before they can run.">
        <ApprovalControl mode={approval} onChange={onApproval} />
      </Section>

      <Section icon={<Lock className="w-4 h-4 text-muted" />} title="API security">
        <div className="text-xs text-muted">
          {auth?.enabled
            ? 'HMAC request signing is enabled — every request is verified.'
            : 'Open (no auth). Set ATHENA_API_SECRET to require signed requests.'}
        </div>
      </Section>
    </Drawer>
  )
}
