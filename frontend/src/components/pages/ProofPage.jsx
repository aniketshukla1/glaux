import React, { useMemo, useState } from 'react'
import { ShieldCheck, ShieldAlert, RefreshCw, Download, Copy, Check, ChevronRight, Loader2, X } from 'lucide-react'
import Page from './Page.jsx'
import { getBlock, exportLedger } from '../../api.js'
import { download } from '../../lib/export.js'
import { ROLE_META, short } from '../../lib/blocks.js'
import { CLI } from '../../lib/brand.js'
import { RoleDot } from '../chat/Trace.jsx'

// The chain, made inspectable: is it intact, what is in it, and how to check
// it without trusting this app at all.

const ACTION_LABEL = {
  PLAN: 'Plan', THINK: 'Thought', CALL_AGENT: 'Hand-off', CAPABILITY_GRANT: 'Capability grant',
  CAPABILITY_REVOKE: 'Capability revoked', MCP_TOOL: 'Tool call', CALL_SKILL: 'Skill run',
  EMIT_OBSERVATION: 'Observation', REFLECT: 'Review', SYNTHESIZE_SKILL: 'New skill',
  COMPACT_CONTEXT: 'Context compacted', EVOLVE_HARNESS: 'Self-improvement', CACHE_HIT: 'Cache hit',
  KEY_ROTATION: 'Key rotation', REQUEST_APPROVAL: 'Approval request',
}
const actionLabel = (t) => ACTION_LABEL[t] || t
const PAGE = 100
const EXPORT_FILE = `${CLI}-ledger.jsonl`

function ago(us) {
  if (!us) return ''
  const s = Math.max(0, Date.now() / 1000 - us / 1e6)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(us / 1000).toLocaleDateString()
}

function CopyButton({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard?.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200) }}
      className="btn-ghost p-1.5" aria-label={label} title={label}>
      {done ? <Check className="w-3.5 h-3.5 text-ok" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

function Field({ label, children }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3 py-1.5 text-[12px]">
      <span className="text-faint">{label}</span>
      <span className="min-w-0 break-all">{children}</span>
    </div>
  )
}

function BlockDetail({ index, meta, roleOf }) {
  const [full, setFull] = useState(null)
  const [err, setErr] = useState('')
  React.useEffect(() => {
    let live = true
    getBlock(index).then((b) => live && setFull(b)).catch(() => live && setErr('Couldn’t load this block.'))
    return () => { live = false }
  }, [index])
  const role = roleOf(meta.agent_id)
  return (
    <div className="px-4 pb-3 pt-1 bg-bg/40 border-t border-line/[0.06] animate-fade-in">
      <Field label="Hash"><span className="mono text-muted">{meta.hash}</span></Field>
      <Field label="Previous">
        <span className="mono text-muted">{meta.index === 0 ? 'genesis' : meta.prev_hash}</span>
      </Field>
      <Field label="Signed by">
        <span className="text-muted">{(ROLE_META[role] || ROLE_META.agent).label}</span>
        <span className="mono text-faint ml-2">{meta.signing_pubkey}</span>
      </Field>
      {full?.signature && <Field label="Signature"><span className="mono text-faint">{full.signature}</span></Field>}
      <div className="mt-2">
        <div className="eyebrow mb-1.5">Payload</div>
        {err ? <p className="text-bad text-[12px]">{err}</p>
          : !full ? <div className="flex items-center gap-2 text-faint text-[12px]"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</div>
            : <pre className="text-[11.5px] leading-relaxed text-muted bg-surface border border-line/[0.08] rounded-md p-3 max-h-72 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(full.payload, null, 2)}</pre>}
      </div>
    </div>
  )
}

export default function ProofPage({ ledger, roleOf, agentsMap, onVerify, focus, onClearFocus }) {
  const { count = 0, blocks = [], verification } = ledger || {}
  const [filter, setFilter] = useState('all')
  const [shown, setShown] = useState(PAGE)
  const [openIdx, setOpenIdx] = useState(null)
  const [busy, setBusy] = useState('')

  const valid = verification ? verification.valid : null
  const focusSet = useMemo(() => (focus?.length ? new Set(focus) : null), [focus])
  const types = useMemo(() => {
    const m = new Map()
    for (const b of blocks) m.set(b.action_type, (m.get(b.action_type) || 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [blocks])
  const rows = useMemo(() => {
    let r = blocks
    if (focusSet) r = r.filter((b) => focusSet.has(b.index))
    else if (filter !== 'all') r = r.filter((b) => b.action_type === filter)
    return [...r].reverse()
  }, [blocks, filter, focusSet])
  const signers = Object.entries(agentsMap || {})
  const last = blocks[blocks.length - 1]

  const reverify = async () => { setBusy('verify'); try { await onVerify() } finally { setBusy('') } }
  const exportProof = async () => {
    setBusy('export')
    try { download(EXPORT_FILE, await exportLedger(), 'application/x-ndjson') } catch { /* surfaced by the API layer */ } finally { setBusy('') }
  }

  return (
    <Page title="Proof" wide
      description="Every step your agents take is signed by the agent that took it and chained to the step before. Change one byte anywhere and verification fails at that exact block."
      actions={
        <>
          <button onClick={reverify} className="btn px-2.5 py-1.5 text-[13px]" disabled={busy === 'verify'}>
            <RefreshCw className={`w-3.5 h-3.5 ${busy === 'verify' ? 'animate-spin' : ''}`} /> Re-verify
          </button>
          <button onClick={exportProof} className="btn-primary px-2.5 py-1.5 text-[13px]" disabled={!count || busy === 'export'}>
            <Download className="w-3.5 h-3.5" /> Export proof
          </button>
        </>
      }>
      {/* status */}
      <section className={`card p-4 flex items-start gap-3.5 ${valid === false ? '!border-bad/40' : ''}`} aria-live="polite">
        <span className={`w-10 h-10 rounded-full grid place-items-center shrink-0 ${valid === false ? 'bg-bad/10 text-bad' : 'bg-ok/10 text-ok'}`}>
          {valid === false ? <ShieldAlert className="w-5 h-5" /> : <ShieldCheck className="w-5 h-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-fg text-[15px] font-semibold">
            {valid === false ? `Tampered at block #${verification.first_bad_index}` : count ? 'Chain verified' : 'No signed steps yet'}
          </h2>
          <p className="text-muted text-[13px] mt-0.5">
            {valid === false ? verification.reason
              : count ? 'Every signature and every hash link checks out, recomputed natively in Rust.'
                : 'Run a task and every step the swarm takes lands here, signed.'}
          </p>
          {count > 0 && (
            <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 text-[12px]">
              <div><dt className="inline text-faint">Blocks </dt><dd className="inline text-fg tabular-nums">{count.toLocaleString()}</dd></div>
              <div><dt className="inline text-faint">Signers </dt><dd className="inline text-fg tabular-nums">{signers.length}</dd></div>
              {last && <div><dt className="inline text-faint">Last block </dt><dd className="inline text-fg">{ago(last.timestamp_us)}</dd></div>}
              {last && <div className="flex items-center gap-1"><dt className="inline text-faint">Head </dt><dd className="inline mono text-muted">{short(last.hash)}</dd><CopyButton text={last.hash} label="Copy head hash" /></div>}
            </dl>
          )}
        </div>
      </section>

      {/* verify yourself */}
      <section className="mt-4 card p-4">
        <h2 className="text-fg text-[13px] font-semibold">Check it without trusting this app</h2>
        <p className="text-muted text-[12.5px] mt-1">Export the chain, then verify it offline with the CLI. No server, no network.</p>
        <div className="mt-2.5 flex items-center gap-2 rounded-md border border-line/[0.1] bg-bg/60 pl-3 pr-1 py-1">
          <code className="flex-1 min-w-0 truncate text-[12.5px] text-fg"><span className="text-faint select-none">$ </span>{CLI} verify --file {EXPORT_FILE}</code>
          <CopyButton text={`${CLI} verify --file ${EXPORT_FILE}`} label="Copy command" />
        </div>
      </section>

      {/* explorer */}
      <section className="mt-8">
        <div className="flex items-center gap-2 mb-2.5">
          <h2 className="text-fg text-[14px] font-semibold flex-1">Blocks</h2>
          {focusSet && (
            <span className="chip !text-accent !border-accent/30 bg-accent/[0.06]">
              Showing {rows.length} blocks from one answer
              <button onClick={onClearFocus} className="ml-0.5 -mr-1 p-0.5 rounded hover:bg-accent/10" aria-label="Show the whole chain"><X className="w-3 h-3" /></button>
            </span>
          )}
        </div>
        {!focusSet && types.length > 1 && (
          <div className="flex flex-wrap gap-1.5 mb-3" role="group" aria-label="Filter by action">
            {[['all', count], ...types].map(([t, n]) => (
              <button key={t} onClick={() => { setFilter(t); setShown(PAGE) }} aria-pressed={filter === t}
                className={`chip transition-colors ${filter === t ? '!text-fg !border-line/30 bg-line/[0.08]' : 'hover:text-fg'}`}>
                {t === 'all' ? 'All' : actionLabel(t)} <span className="text-faint tabular-nums">{n}</span>
              </button>
            ))}
          </div>
        )}
        {rows.length === 0 ? (
          <div className="card p-8 text-center text-faint text-[13px]">Nothing signed yet.</div>
        ) : (
          <div className="card overflow-hidden divide-y divide-line/[0.06]">
            {rows.slice(0, shown).map((b) => {
              const role = roleOf(b.agent_id)
              const open = openIdx === b.index
              return (
                <div key={b.index}>
                  <button onClick={() => setOpenIdx(open ? null : b.index)} aria-expanded={open}
                    className="w-full flex items-center gap-3 px-4 py-2 text-left text-[12.5px] hover:bg-line/[0.035] transition-colors">
                    <span className="text-faint tabular-nums w-10 shrink-0">#{b.index}</span>
                    <span className="text-fg w-36 shrink-0 truncate">{actionLabel(b.action_type)}</span>
                    <span className="flex items-center gap-1.5 min-w-0 flex-1">
                      <RoleDot role={role} size={16} />
                      <span className="text-muted truncate">{(ROLE_META[role] || ROLE_META.agent).label}</span>
                    </span>
                    <span className="text-faint w-20 shrink-0 text-right hidden sm:block">{ago(b.timestamp_us)}</span>
                    <span className="hash w-28 shrink-0 text-right hidden md:block">{short(b.hash)}</span>
                    <ChevronRight className={`w-3.5 h-3.5 text-faint shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />
                  </button>
                  {open && <BlockDetail index={b.index} meta={b} roleOf={roleOf} />}
                </div>
              )
            })}
          </div>
        )}
        {rows.length > shown && (
          <div className="flex justify-center mt-3">
            <button onClick={() => setShown((n) => n + PAGE)} className="btn px-3 py-1.5 text-[12.5px]">
              Show {Math.min(PAGE, rows.length - shown)} older
            </button>
          </div>
        )}
      </section>

      {/* signers */}
      {signers.length > 0 && (
        <section className="mt-8">
          <h2 className="text-fg text-[14px] font-semibold mb-1">Signers</h2>
          <p className="text-faint text-[12.5px] mb-2.5">Each agent holds its own Ed25519 key. A block is only valid if the agent that claims it really signed it.</p>
          <div className="card divide-y divide-line/[0.06]">
            {signers.map(([id, role]) => (
              <div key={id} className="flex items-center gap-3 px-4 py-2 text-[12.5px]">
                <RoleDot role={role} size={18} />
                <span className="text-fg w-32 shrink-0">{(ROLE_META[role] || ROLE_META.agent).label}</span>
                <span className="mono text-faint truncate flex-1">{id}</span>
                <CopyButton text={id} label="Copy key" />
              </div>
            ))}
          </div>
        </section>
      )}
    </Page>
  )
}
