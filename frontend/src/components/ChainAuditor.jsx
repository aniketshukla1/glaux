import React, { useState } from 'react'
import { Link2, Download } from 'lucide-react'
import { exportLedger } from '../api.js'
import { download } from '../lib/export.js'

export default function ChainAuditor({ ledger, onVerify }) {
  const v = ledger.verification
  const ok = v && v.valid
  const [busy, setBusy] = useState(false)

  const onExport = async () => {
    setBusy(true)
    try {
      download('athena-ledger.jsonl', await exportLedger(), 'application/x-ndjson')
    } catch { /* ignore */ } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2 className="text-fg mb-3 flex items-center gap-2"><Link2 className="w-4 h-4 text-accent" /> Chain Auditor</h2>
      <div className="glass p-4 space-y-3">
        <div
          className={`p-3 rounded-lg border text-sm ${
            ok
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-rose-500/40 bg-rose-500/10 text-rose-300'
          }`}
        >
          {ok
            ? '✓ Chain verified — every signature and hash-link valid'
            : v
              ? `✗ Tamper detected at block #${v.first_bad_index}: ${v.reason}`
              : '— no chain yet —'}
        </div>

        <div className="flex justify-between text-sm text-muted">
          <span>Blocks</span>
          <span className="text-fg">{ledger.count}</span>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onVerify}
            className="flex-1 px-3 py-2 rounded-lg border border-accent2/40 text-accent2 hover:bg-accent2/10 transition"
          >
            Re-verify chain
          </button>
          <button
            onClick={onExport}
            disabled={busy || !ledger.count}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line/20 text-muted hover:text-fg hover:border-line/40 transition disabled:opacity-40"
            title="Download the signed chain as a proof anyone can verify offline"
          >
            <Download className="w-3.5 h-3.5" /> Export proof
          </button>
        </div>

        <p className="text-xs text-faint leading-relaxed">
          Verification runs natively in Rust (athena_ledger): it recomputes every
          SHA-256, checks each prev-hash link, and validates every Ed25519 signature.
          The chain is durable across restarts; <span className="text-muted">Export proof</span> downloads it
          as <code className="text-muted">athena-ledger.jsonl</code> — verify it independently with{' '}
          <code className="text-muted">python scripts/verify_ledger.py</code>.
        </p>
      </div>
    </section>
  )
}
