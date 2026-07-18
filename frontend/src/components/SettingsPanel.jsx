import React, { useEffect, useState } from 'react'
import {
  Settings, Palette, ShieldHalf, Cpu, Lock, Check, UserCog, KeyRound, LogOut, Trash2, Loader2, X, Sparkles, BookMarked,
  SlidersHorizontal,
} from 'lucide-react'
import { getFsWorkspace, setFsWorkspace } from '../api.js'
import Modal from './Modal.jsx'
import LlmControl from './LlmControl.jsx'
import SafetyControl from './SafetyControl.jsx'
import ApprovalControl from './ApprovalControl.jsx'
import UserAvatar from './UserAvatar.jsx'
import Personas from './Personas.jsx'
import Recipes from './Recipes.jsx'

const THEMES = [
  { key: 'dark', label: 'Dark', bg: '#090b10', surface: '#11151e', accent: '#2dd4bf', fg: '#e2e8f0' },
  { key: 'light', label: 'Light', bg: '#fafaf9', surface: '#ffffff', accent: '#0d9488', fg: '#0f172a' },
  { key: 'oled', label: 'OLED', bg: '#000000', surface: '#0c0c0e', accent: '#2dd4bf', fg: '#ededf0' },
  { key: 'midnight', label: 'Midnight', bg: '#080c1c', surface: '#10162c', accent: '#38bdf8', fg: '#e0e7f5' },
  { key: 'nord', label: 'Nord', bg: '#2e3440', surface: '#3b4252', accent: '#88c0d0', fg: '#d8dee9' },
  { key: 'ember', label: 'Ember', bg: '#18100e', surface: '#261a16', accent: '#fb923c', fg: '#f5ece6' },
]

const TABS = [
  { key: 'account', label: 'Account', Icon: UserCog },
  { key: 'personas', label: 'Personas', Icon: Sparkles },
  { key: 'recipes', label: 'Recipes', Icon: BookMarked },
  { key: 'appearance', label: 'Appearance', Icon: Palette },
  { key: 'model', label: 'Model', Icon: Cpu },
  { key: 'advanced', label: 'Advanced', Icon: SlidersHorizontal },
  { key: 'safety', label: 'Safety', Icon: ShieldHalf },
  { key: 'security', label: 'Security', Icon: Lock },
]

function Input(props) {
  return (
    <input
      {...props}
      className="w-full glass px-3.5 py-2.5 rounded-lg bg-transparent outline-none text-sm text-fg placeholder-faint focus:border-line/30"
    />
  )
}

// A titled block with a hairline divider above it (except the first), for clear
// separation between Account sections.
function Section({ title, hint, children, first }) {
  return (
    <div className={first ? '' : 'mt-7 pt-7 border-t border-line/10'}>
      <div className="text-fg text-sm font-medium">{title}</div>
      {hint && <p className="text-faint text-xs mt-1 mb-4">{hint}</p>}
      {children}
    </div>
  )
}

function Btn({ children, onClick, busy, disabled, danger, kind = 'border' }) {
  const base = 'px-3 py-2 rounded-lg text-sm inline-flex items-center justify-center gap-1.5 transition disabled:opacity-50'
  const styles = danger
    ? 'border border-rose-500/40 text-rose-300 hover:bg-rose-500/10'
    : kind === 'accent'
      ? 'btn-accent'
      : 'border border-line/16 text-muted hover:text-fg hover:border-line/30'
  return (
    <button onClick={onClick} disabled={busy || disabled} className={`${base} ${styles}`}>
      {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}{children}
    </button>
  )
}

function Notice({ msg }) {
  if (!msg) return null
  const ok = msg.kind === 'ok'
  return <div className={`text-xs mt-2 ${ok ? 'text-emerald-400' : 'text-rose-400'}`}>{msg.text}</div>
}

function AccountTab({ user, onUpdateProfile, onChangePassword, onSignOut, onSignOutEverywhere, onDeleteAccount }) {
  const [name, setName] = useState(user?.name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileMsg, setProfileMsg] = useState(null)

  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pwBusy, setPwBusy] = useState(false)
  const [pwMsg, setPwMsg] = useState(null)

  const [confirmDelete, setConfirmDelete] = useState(false)
  const dirty = name !== (user?.name || '') || email !== (user?.email || '')

  const saveProfile = async () => {
    setProfileBusy(true); setProfileMsg(null)
    try {
      await onUpdateProfile({ name, email })
      setProfileMsg({ kind: 'ok', text: 'Saved.' })
    } catch (e) {
      setProfileMsg({ kind: 'err', text: e.message })
    } finally { setProfileBusy(false) }
  }

  const savePassword = async () => {
    if (next !== confirm) { setPwMsg({ kind: 'err', text: "New passwords don't match." }); return }
    setPwBusy(true); setPwMsg(null)
    try {
      await onChangePassword(cur, next)
      setCur(''); setNext(''); setConfirm('')
      setPwMsg({ kind: 'ok', text: 'Password updated.' })
    } catch (e) {
      setPwMsg({ kind: 'err', text: e.message })
    } finally { setPwBusy(false) }
  }

  return (
    <div>
      <div className="flex items-center gap-3.5 pb-6 mb-1 border-b border-line/10">
        <UserAvatar user={{ ...user, name, email }} size={52} />
        <div className="min-w-0">
          <div className="text-fg text-[15px] font-medium truncate">{name || email}</div>
          <div className="text-faint text-xs truncate mt-0.5">{email}</div>
        </div>
      </div>

      <Section title="Profile" hint="Your display name and email." first>
        <div className="space-y-2.5">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" type="email" />
        </div>
        <div className="mt-3.5 flex items-center gap-3">
          <Btn onClick={saveProfile} busy={profileBusy} disabled={!dirty} kind="accent">Save changes</Btn>
          <Notice msg={profileMsg} />
        </div>
      </Section>

      <Section title="Change password" hint="You'll stay signed in on this device.">
        <div className="space-y-2.5">
          <Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} placeholder="Current password" autoComplete="current-password" />
          <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="New password" autoComplete="new-password" />
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirm new password" autoComplete="new-password" />
        </div>
        <div className="mt-3.5 flex items-center gap-3">
          <Btn onClick={savePassword} busy={pwBusy} disabled={!cur || !next}><KeyRound className="w-3.5 h-3.5" /> Update password</Btn>
          <Notice msg={pwMsg} />
        </div>
      </Section>

      <Section title="Danger zone" hint="Sign out, or permanently delete your account and all its data.">
        <div className="flex flex-wrap gap-2">
          <Btn onClick={onSignOut}><LogOut className="w-3.5 h-3.5" /> Sign out</Btn>
          <Btn onClick={onSignOutEverywhere}>Sign out everywhere</Btn>
          {!confirmDelete ? (
            <Btn danger onClick={() => setConfirmDelete(true)}><Trash2 className="w-3.5 h-3.5" /> Delete account</Btn>
          ) : (
            <Btn danger onClick={onDeleteAccount}><Trash2 className="w-3.5 h-3.5" /> Confirm delete — permanent</Btn>
          )}
        </div>
      </Section>
    </div>
  )
}

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

function Toggle({ on, busy, onChange }) {
  return (
    <button
      onClick={() => onChange(!on)} disabled={busy} role="switch" aria-checked={on}
      className={`relative w-11 h-6 rounded-full transition shrink-0 disabled:opacity-50 ${on ? 'bg-accent' : 'bg-line/25'}`}
    >
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

function StatRow({ label, value }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-muted text-sm">{label}</span>
      <span className="text-fg text-xs font-mono">{value}</span>
    </div>
  )
}

// Runtime capabilities: the jailed workspace file tools (toggle) and the
// long-horizon context-management budget (read-only, from /api/health).
function AdvancedTab({ health, onRefresh }) {
  const [ws, setWs] = useState(null)
  const [wsBusy, setWsBusy] = useState(false)
  const [wsMsg, setWsMsg] = useState(null)
  const ctx = health?.context

  useEffect(() => { getFsWorkspace().then(setWs).catch(() => {}) }, [])

  const toggleWs = async (next) => {
    setWsBusy(true); setWsMsg(null)
    try {
      setWs(await setFsWorkspace(next))
      setWsMsg({ kind: 'ok', text: next ? 'File tools enabled.' : 'File tools disabled.' })
      onRefresh && onRefresh()
    } catch (e) {
      setWsMsg({ kind: 'err', text: e.message })
    } finally { setWsBusy(false) }
  }

  return (
    <div>
      <Section
        title="Workspace file tools"
        hint="Let the swarm create real files in one jailed, size-capped directory it can never escape. Every write is signed to the ledger."
        first
      >
        <div className="glass rounded-lg px-4 py-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="text-fg text-sm">{ws?.enabled ? 'Enabled' : 'Disabled'}</div>
            <div className="text-faint text-xs truncate mt-0.5 font-mono">{ws?.root || '—'}</div>
          </div>
          <Toggle on={!!ws?.enabled} busy={wsBusy} onChange={toggleWs} />
        </div>
        {ws?.enabled && (
          <div className="text-faint text-xs mt-2">{(ws.files || []).length} file(s) in the workspace</div>
        )}
        <Notice msg={wsMsg} />
      </Section>

      <Section
        title="Context management"
        hint="Long runs stay under a fixed prompt budget: recent steps kept verbatim, older ones digested to one line, deepest history elided — every compaction signed to the ledger."
      >
        <div className="glass rounded-lg px-4 py-1 divide-y divide-line/8">
          <StatRow label="History budget" value={ctx ? `${ctx.max_history_chars.toLocaleString()} chars` : '—'} />
          <StatRow label="Recent steps kept verbatim" value={ctx ? ctx.keep_recent_steps : '—'} />
          <StatRow label="Per-thought clip" value={ctx ? `${ctx.thought_chars} chars` : '—'} />
          <StatRow label="Per-observation clip" value={ctx ? `${ctx.obs_chars} chars` : '—'} />
          <StatRow label="LLM summarizer" value={ctx ? (ctx.summarize ? 'on' : 'off · deterministic') : '—'} />
        </div>
        <p className="text-faint text-xs mt-2">Tune with the <span className="font-mono">ATHENA_CONTEXT_*</span> environment variables.</p>
      </Section>
    </div>
  )
}

export default function SettingsPanel({
  open, onClose, theme, onSetTheme, safety, onSafety, approval, onApproval, auth,
  initialTab, user, onUpdateProfile, onChangePassword, onSignOut, onSignOutEverywhere, onDeleteAccount,
  personas, onCreatePersona, onUpdatePersona, onDeletePersona,
  recipes, onCreateRecipe, onUpdateRecipe, onDeleteRecipe,
  health, onRefresh,
}) {
  const [tab, setTab] = useState(initialTab || 'account')
  useEffect(() => { if (open) setTab(initialTab || 'account') }, [open, initialTab])
  return (
    <Modal open={open} onClose={onClose} className="max-w-4xl">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-line/10 shrink-0">
        <Settings className="w-4 h-4 text-muted" />
        <h2 className="text-fg font-medium">Settings</h2>
        <button onClick={onClose} className="btn p-1.5 ml-auto" aria-label="Close"><X className="w-4 h-4" /></button>
      </div>

      <div className="flex flex-1 min-h-0">
        <nav className="w-48 sm:w-52 shrink-0 border-r border-line/10 p-3 space-y-0.5 overflow-y-auto">
          {TABS.map(({ key, label, Icon }) => (
            <button key={key} onClick={() => setTab(key)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition ${
                tab === key ? 'text-fg bg-line/10 font-medium' : 'text-muted hover:text-fg hover:bg-line/5'
              }`}>
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-6 sm:px-10 py-8">
            {tab === 'account' && (
              <AccountTab
                user={user}
                onUpdateProfile={onUpdateProfile}
                onChangePassword={onChangePassword}
                onSignOut={onSignOut}
                onSignOutEverywhere={onSignOutEverywhere}
                onDeleteAccount={onDeleteAccount}
              />
            )}

            {tab === 'personas' && (
              <Field title="Personas" hint="Custom assistants you can apply to any chat.">
                <Personas personas={personas} onCreate={onCreatePersona} onUpdate={onUpdatePersona} onDelete={onDeletePersona} />
              </Field>
            )}

            {tab === 'recipes' && (
              <Field title="Recipes" hint="Saved task templates — run them from the composer with “/”.">
                <Recipes recipes={recipes} onCreate={onCreateRecipe} onUpdate={onUpdateRecipe} onDelete={onDeleteRecipe} />
              </Field>
            )}

            {tab === 'appearance' && (
              <Field title="Theme" hint="Pick a look — the whole app follows it.">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {THEMES.map((t) => <ThemeSwatch key={t.key} t={t} active={theme === t.key} onPick={onSetTheme} />)}
                </div>
              </Field>
            )}

            {tab === 'model' && (
              <Field title="Model" hint="Run the swarm on any of 30+ providers — OpenAI, Gemini, Grok, DeepSeek, Mistral, Sarvam, Groq, OpenRouter, local models, or the offline demo.">
                <LlmControl />
              </Field>
            )}

            {tab === 'advanced' && <AdvancedTab health={health} onRefresh={onRefresh} />}

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
          </div>
        </div>
      </div>
    </Modal>
  )
}
