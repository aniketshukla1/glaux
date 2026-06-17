import React, { useState } from 'react'
import { Loader2, ArrowRight, Mail, Lock, User as UserIcon } from 'lucide-react'
import { signup, login, setToken } from '../api.js'
import ConstellationSphere from './ConstellationSphere.jsx'

function Input({ icon: Icon, value, onChange, type = 'text', ...props }) {
  return (
    <div className="glass flex items-center gap-2.5 px-3.5 rounded-xl">
      <Icon className="w-4 h-4 text-faint shrink-0" />
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-transparent outline-none text-fg text-sm placeholder-faint py-2.5"
        {...props}
      />
    </div>
  )
}

// Full-screen sign-in / sign-up gate. On success it stores the session token and
// hands the user object back up to the app.
export default function AuthScreen({ firstRun, onAuthed }) {
  const [mode, setMode] = useState(firstRun ? 'signup' : 'login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const signupMode = mode === 'signup'

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const out = signupMode
        ? await signup(email.trim(), password, name.trim())
        : await login(email.trim(), password)
      setToken(out.token)
      onAuthed(out.user)
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-5 animate-fade-in">
      <ConstellationSphere size={150} />
      <h1 className="text-fg text-2xl font-medium tracking-tight -mt-3 text-center">
        {signupMode ? (firstRun ? 'Create your Athena account' : 'Create an account') : 'Welcome back'}
      </h1>
      <p className="text-muted text-sm mt-2 text-center">
        {signupMode ? 'Your projects, chats, and skills — private to you.' : 'Sign in to your workspace.'}
      </p>

      <form onSubmit={submit} className="w-full max-w-sm mt-7 space-y-2.5">
        {signupMode && (
          <Input icon={UserIcon} placeholder="Your name" value={name} onChange={setName} autoFocus />
        )}
        <Input icon={Mail} type="email" placeholder="Email" value={email} onChange={setEmail}
          autoFocus={!signupMode} autoComplete="email" required />
        <Input icon={Lock} type="password" placeholder="Password" value={password} onChange={setPassword}
          autoComplete={signupMode ? 'new-password' : 'current-password'} required />
        {error && <div className="text-rose-400 text-xs px-1 animate-fade-in">{error}</div>}
        <button type="submit" disabled={busy || !email || !password}
          className="btn-accent w-full py-2.5 flex items-center justify-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" />
            : <>{signupMode ? 'Create account' : 'Sign in'} <ArrowRight className="w-4 h-4" /></>}
        </button>
      </form>

      <button onClick={() => { setError(''); setMode(signupMode ? 'login' : 'signup') }}
        className="text-sm text-muted hover:text-fg mt-5 transition">
        {signupMode ? 'Already have an account? Sign in' : 'New here? Create an account'}
      </button>
    </div>
  )
}
