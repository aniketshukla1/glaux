import React, { useState } from 'react'
import { Loader2, ArrowRight, Mail, Lock, User as UserIcon, ArrowLeft } from 'lucide-react'
import {
  login, setToken, signupWithInvite, oauthStart, forgotPassword, resetPassword,
} from '../api.js'
import ConstellationSphere from './ConstellationSphere.jsx'
import SwarmField from './SwarmField.jsx'
import { BRAND } from '../lib/brand.js'

function Input({ icon: Icon, value, onChange, type = 'text', ...props }) {
  return (
    <div className="glass flex items-center gap-2.5 px-3.5 rounded-xl">
      <Icon className="w-4 h-4 text-faint shrink-0" />
      <input
        type={type} value={value} onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-transparent outline-none text-fg text-sm placeholder-faint py-2.5"
        {...props}
      />
    </div>
  )
}

const PROVIDER_LABEL = { google: 'Google', github: 'GitHub' }

function OAuthButtons({ providers }) {
  if (!providers?.length) return null
  const go = async (id) => {
    try { const { url } = await oauthStart(id); window.location.href = url } catch { /* ignore */ }
  }
  return (
    <div className="w-full max-w-sm mt-6">
      <div className="space-y-2">
        {providers.map((p) => (
          <button key={p.id} onClick={() => go(p.id)}
            className="btn w-full py-2.5 flex items-center justify-center gap-2 text-sm">
            Continue with {PROVIDER_LABEL[p.id] || p.label || p.id}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-3 my-5 text-faint text-xs">
        <span className="h-px flex-1 bg-line/15" /> or <span className="h-px flex-1 bg-line/15" />
      </div>
    </div>
  )
}

// Sign-in / sign-up / forgot / reset gate. On success it stores the session token
// and hands the user object up to the app.
export default function AuthScreen({ firstRun, onAuthed, oauthProviders = [], invite = '', resetToken = '', initialError = '' }) {
  const [mode, setMode] = useState(resetToken ? 'reset' : firstRun ? 'signup' : 'login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(initialError)
  const [info, setInfo] = useState(null)   // { text, link? }

  const reset = (m) => { setError(''); setInfo(null); setPassword(''); setMode(m) }

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setInfo(null)
    try {
      if (mode === 'forgot') {
        const out = await forgotPassword(email.trim())
        setInfo({ text: 'If that email has an account, a reset link is on its way.', link: out.dev_link })
      } else if (mode === 'reset') {
        const out = await resetPassword(resetToken, password)
        setToken(out.token); onAuthed(out.user)
      } else if (mode === 'signup') {
        const out = await signupWithInvite(email.trim(), password, name.trim(), invite)
        setToken(out.token); onAuthed(out.user)
      } else {
        const out = await login(email.trim(), password)
        setToken(out.token); onAuthed(out.user)
      }
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const heading = {
    login: 'Welcome back',
    signup: firstRun ? `Create your ${BRAND} account` : 'Create an account',
    forgot: 'Reset your password',
    reset: 'Choose a new password',
  }[mode]
  const sub = {
    login: 'Sign in to your workspace.',
    signup: 'Your projects, chats, and skills — private to you.',
    forgot: "Enter your email and we'll send a reset link.",
    reset: 'Pick a strong password to finish.',
  }[mode]
  const cta = { login: 'Sign in', signup: 'Create account', forgot: 'Send reset link', reset: 'Set password' }[mode]

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-5 py-10 animate-fade-in overflow-hidden">
      <SwarmField className="absolute inset-0 w-full h-full" opacity={0.75} />
      <div className="relative z-10 w-full flex flex-col items-center">
      <ConstellationSphere size={300} owlRatio={0.36} />
      <h1 className="text-fg text-2xl font-medium tracking-tight mt-4 text-center">{heading}</h1>
      <p className="text-muted text-sm mt-2 text-center max-w-sm">{sub}</p>

      {(mode === 'login' || mode === 'signup') && <OAuthButtons providers={oauthProviders} />}

      <form onSubmit={submit} className={`w-full max-w-sm space-y-2.5 ${(mode === 'login' || mode === 'signup') && oauthProviders.length ? '' : 'mt-7'}`}>
        {mode === 'signup' && <Input icon={UserIcon} placeholder="Your name" value={name} onChange={setName} autoFocus />}
        {mode !== 'reset' && (
          <Input icon={Mail} type="email" placeholder="Email" value={email} onChange={setEmail}
            autoFocus={mode !== 'signup'} autoComplete="email" required />
        )}
        {mode !== 'forgot' && (
          <Input icon={Lock} type="password" placeholder={mode === 'reset' ? 'New password' : 'Password'}
            value={password} onChange={setPassword} autoFocus={mode === 'reset'}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required />
        )}
        {error && <div className="text-bad text-xs px-1 animate-fade-in">{error}</div>}
        {info && (
          <div className="text-ok text-xs px-1 animate-fade-in">
            {info.text}
            {info.link && (
              <button type="button" onClick={() => { window.location.href = info.link }}
                className="block mt-1 text-accent underline underline-offset-2">Open reset link (dev)</button>
            )}
          </div>
        )}
        <button type="submit" disabled={busy || (mode !== 'reset' && mode !== 'forgot' && (!email || !password))}
          className="btn-accent w-full py-2.5 flex items-center justify-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <>{cta} <ArrowRight className="w-4 h-4" /></>}
        </button>
      </form>

      <div className="mt-5 text-sm flex flex-col items-center gap-2">
        {mode === 'login' && (
          <>
            <button onClick={() => reset('forgot')} className="text-muted hover:text-fg transition">Forgot your password?</button>
            <button onClick={() => reset('signup')} className="text-muted hover:text-fg transition">New here? Create an account</button>
          </>
        )}
        {mode === 'signup' && !firstRun && (
          <button onClick={() => reset('login')} className="text-muted hover:text-fg transition">Already have an account? Sign in</button>
        )}
        {(mode === 'forgot' || mode === 'reset') && (
          <button onClick={() => reset('login')} className="text-muted hover:text-fg transition inline-flex items-center gap-1">
            <ArrowLeft className="w-3.5 h-3.5" /> Back to sign in
          </button>
        )}
      </div>
      </div>
    </div>
  )
}
