import React, { useEffect, useState } from 'react'
import { Users, Shield, ShieldOff, UserCheck, UserX, Trash2, Link2, Copy, Check, Loader2 } from 'lucide-react'
import { getAdminUsers, updateAdminUser, deleteAdminUser, createInvite } from '../api.js'
import UserAvatar from './UserAvatar.jsx'

export default function AdminPanel({ currentUserId }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [invite, setInvite] = useState('')
  const [copied, setCopied] = useState(false)

  const load = async () => {
    try { setUsers((await getAdminUsers()).users); setError('') }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const patch = async (id, body) => { try { await updateAdminUser(id, body); await load() } catch (e) { setError(e.message) } }
  const remove = async (id) => { try { await deleteAdminUser(id); await load() } catch (e) { setError(e.message) } }
  const makeInvite = async () => {
    try { const out = await createInvite(); setInvite(out.link); setCopied(false) } catch (e) { setError(e.message) }
  }
  const copyInvite = () => { navigator.clipboard?.writeText(invite); setCopied(true); setTimeout(() => setCopied(false), 1200) }

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-fg flex items-center gap-2"><Users className="w-4 h-4 text-accent" /> Team <span className="text-xs text-faint">({users.length})</span></h2>
        <button onClick={makeInvite} className="btn px-2.5 py-1.5 text-sm flex items-center gap-1.5"><Link2 className="w-3.5 h-3.5" /> Invite</button>
      </div>

      {invite && (
        <div className="glass p-2.5 mb-3 flex items-center gap-2">
          <input readOnly value={invite} className="flex-1 bg-transparent outline-none text-xs text-muted truncate" />
          <button onClick={copyInvite} className="btn px-2 py-1 text-xs flex items-center gap-1">
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}{copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}
      {error && <div className="text-rose-400 text-xs mb-3">{error}</div>}
      {loading && <div className="text-faint text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>}

      <div className="space-y-2 max-h-[60vh] overflow-auto pr-1">
        {users.map((u) => {
          const self = u.id === currentUserId
          return (
            <div key={u.id} className={`glass p-3 flex items-center gap-3 ${u.is_active ? '' : 'opacity-60'}`}>
              <UserAvatar user={u} size={36} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-fg text-sm truncate">{u.name}</span>
                  {u.is_admin && <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/30">admin</span>}
                  {!u.email_verified && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">unverified</span>}
                  {!u.is_active && <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30">disabled</span>}
                  {self && <span className="text-[10px] text-faint">you</span>}
                </div>
                <div className="text-faint text-xs truncate">{u.email}{u.oauth?.length ? ` · ${u.oauth.join(', ')}` : ''}</div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => patch(u.id, { is_admin: !u.is_admin })} title={u.is_admin ? 'Revoke admin' : 'Make admin'}
                  className="btn p-1.5">{u.is_admin ? <ShieldOff className="w-3.5 h-3.5" /> : <Shield className="w-3.5 h-3.5" />}</button>
                {!self && (
                  <>
                    <button onClick={() => patch(u.id, { is_active: !u.is_active })} title={u.is_active ? 'Deactivate' : 'Activate'}
                      className="btn p-1.5">{u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}</button>
                    <button onClick={() => remove(u.id)} title="Delete user"
                      className="btn p-1.5 text-rose-300 hover:text-rose-200"><Trash2 className="w-3.5 h-3.5" /></button>
                  </>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
