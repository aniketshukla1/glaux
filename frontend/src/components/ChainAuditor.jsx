import React from 'react'

export default function ChainAuditor({ ledger, onVerify }) {
  const v = ledger.verification
  const ok = v && v.valid

  return (
    <section>
      <h2 className="text-slate-300 mb-3">☍ Chain Auditor</h2>
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

        <div className="flex justify-between text-sm text-slate-400">
          <span>Blocks</span>
          <span className="text-slate-200">{ledger.count}</span>
        </div>

        <button
          onClick={onVerify}
          className="w-full px-3 py-2 rounded-lg border border-athena-accent2/40 text-athena-accent2 hover:bg-athena-accent2/10 transition"
        >
          Re-verify chain
        </button>

        <p className="text-xs text-slate-500 leading-relaxed">
          Verification runs natively in Rust (athena_ledger): it recomputes every
          SHA-256, checks each prev-hash link, and validates every Ed25519 signature.
        </p>
      </div>
    </section>
  )
}
