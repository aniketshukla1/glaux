import Link from "next/link";
import Image from "next/image";
import {
  ShieldCheck,
  Hammer,
  RefreshCw,
  Gauge,
  Lock,
  Terminal,
  ArrowRight,
  Check,
} from "lucide-react";
import { SwarmField } from "./components/SwarmField";
import { Logo } from "./components/Logo";

const REPO = "https://github.com/athena-swarm/athena";

const features = [
  {
    icon: ShieldCheck,
    title: "It proves its work",
    body: "Every action is Ed25519-signed by the agent that took it and appended to a hash-chained ledger. Tamper with a block and the chain breaks. Tracing tells you what a system claims it did; a signed chain lets you prove it.",
  },
  {
    icon: Hammer,
    title: "It builds its own tools",
    body: "When nothing fits, an agent writes a skill. Athena static-capability-checks it, runs its generated tests in the sandbox, and injects it into the live run. Proven skills get promoted; failing ones get repaired and retried.",
  },
  {
    icon: RefreshCw,
    title: "It can't get worse",
    body: "The harness tunes its own routing, budgets, prompts, playbooks and tool library from outcomes. Every self-modification is evidence-gated, signed to the ledger, and reversible.",
  },
  {
    icon: Gauge,
    title: "It doesn't overpay",
    body: "A sub-millisecond embedding router sends trivial asks to a one-shot responder and only escalates real work to the full swarm — and it learns from mis-routed runs. An opt-in semantic cache answers repeats with zero model calls.",
  },
  {
    icon: Lock,
    title: "Capability-zero sandbox",
    body: "Model-written code runs in a WebAssembly guest with no ambient authority — it cannot syscall by default. File access is a separate, opt-in jailed workspace with size caps.",
  },
  {
    icon: Terminal,
    title: "Yours, and local",
    body: "Runs entirely offline on Ollama with a native Rust core. No vendor lock-in, no telemetry, Apache-2.0 licensed. Drive it from a dashboard, a full-parity CLI, or the HTTP API.",
  },
];

const comparison: [string, string, string][] = [
  ["Audit trail", "Signed, hash-chained ledger", "Tracing / logs"],
  ["New tools", "Synthesized + sandbox-tested at runtime", "Pre-registered by you"],
  ["Self-improvement", "Gated, signed, reversible", "Manual tuning"],
  ["Cost control", "Learned tiering + semantic cache", "Usually one model per call"],
  ["Isolation", "WASM, zero ambient authority", "Often “enforce at the tool level”"],
];

const docLinks = [
  ["Getting started", "Install, first run, first swarm", "/docs/getting-started"],
  ["Architecture", "Swarm, ledger, sandbox, memory", "/docs/architecture"],
  ["Self-evolving harness", "How Athena improves itself", "/docs/self-evolution"],
  ["CLI reference", "Every athena command", "/docs/cli"],
  ["HTTP API", "The stable endpoint surface", "/docs/api"],
  ["Security model", "Sandbox, jail, ledger, trade-offs", "/docs/security"],
];

export default function Home() {
  return (
    <main>
      {/* Hero */}
      <section className="relative flex min-h-[86vh] flex-col items-center justify-center overflow-hidden px-6 py-24 text-center">
        <SwarmField className="absolute inset-0 h-full w-full" />
        <div className="relative z-10 max-w-3xl animate-fade-up">
          <div className="mx-auto mb-7 w-fit drop-shadow-[0_0_20px_rgb(var(--accent)/0.45)]">
            <Logo size={72} />
          </div>
          <h1 className="text-[clamp(30px,7vw,62px)] font-semibold leading-[1.07] tracking-tight">
            A multi-agent swarm
            <br />
            that <span className="gradient-text">proves its work</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-lg text-muted">
            Athena turns a goal into a team of agents that plan, execute in parallel, and verify each
            other — then signs every step onto a tamper-evident ledger. It writes its own tools when
            none exist, and improves itself without being able to get worse.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <a
              href={REPO}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-accent to-accent2 px-5 py-3 text-sm font-medium text-[#04121a] transition hover:brightness-110"
            >
              Get started <ArrowRight className="h-4 w-4" />
            </a>
            <Link
              href="#different"
              className="inline-flex items-center gap-2 rounded-xl border border-line/20 px-5 py-3 text-sm font-medium text-fg transition hover:border-line/40 hover:bg-line/5"
            >
              What makes it different
            </Link>
          </div>
          <div className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13px] text-faint">
            <span>
              <b className="font-semibold text-accent">Signed</b> provenance
            </span>
            <span>
              <b className="font-semibold text-accent">Local-first</b> — runs offline
            </span>
            <span>
              <b className="font-semibold text-accent">Apache-2.0</b>
            </span>
          </div>
        </div>
      </section>

      {/* Demo */}
      <section className="mx-auto -mt-6 max-w-3xl px-6">
        <div className="overflow-hidden rounded-2xl border border-line/12 shadow-2xl shadow-black/50">
          <Image
            src="/images/demo.gif"
            alt="Athena running a task, streaming the swarm, and verifying the signed ledger"
            width={800}
            height={470}
            className="w-full"
            unoptimized
            priority
          />
        </div>
      </section>

      {/* Quickstart */}
      <section className="mx-auto max-w-content px-6 py-24">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Quickstart</p>
        <h2 className="mt-3 text-[clamp(26px,3.6vw,34px)] font-semibold tracking-tight">
          Running in three commands
        </h2>
        <p className="mt-3 max-w-xl text-muted">
          No API key required — Athena runs fully local on Ollama, or against 30+ hosted providers.
        </p>
        <pre className="glass mt-7 overflow-x-auto rounded-xl p-5 text-[13.5px] leading-relaxed">
          <code>
            <span className="text-faint"># clone, build the native ledger kernel + dashboard</span>
            {"\n"}git clone https://github.com/athena-swarm/athena && <span className="text-accent">cd</span> athena
            {"\n"}./install.sh
            {"\n\n"}
            <span className="text-faint"># start the swarm → http://127.0.0.1:8000</span>
            {"\n"}./venv/bin/athena up
            {"\n\n"}
            <span className="text-faint"># or drive it straight from the terminal</span>
            {"\n"}athena run <span className="text-accent">&quot;research the top vector databases and write a comparison&quot;</span>
            {"\n"}athena verify   <span className="text-faint"># ✓ chain verified · every step signed</span>
          </code>
        </pre>
      </section>

      {/* Differentiators */}
      <section id="different" className="border-t border-line/10">
        <div className="mx-auto max-w-content px-6 py-24">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Why Athena</p>
          <h2 className="mt-3 text-[clamp(26px,3.6vw,34px)] font-semibold tracking-tight">
            What makes it different
          </h2>
          <p className="mt-3 max-w-2xl text-muted">
            Most frameworks give you orchestration and observability. Athena adds two things they
            structurally don&apos;t have — provable provenance and genuine self-extension — and makes
            both safe by construction.
          </p>

          <div className="mt-11 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div
                key={f.title}
                className="glass rounded-2xl p-6 transition hover:-translate-y-0.5 hover:border-accent/35"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/14 text-accent">
                  <f.icon className="h-[18px] w-[18px]" />
                </div>
                <h3 className="mt-4 font-semibold text-fg">{f.title}</h3>
                <p className="mt-2 text-sm text-muted">{f.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-faint">
                  <th className="border-b border-line/12 px-4 py-3 font-semibold" />
                  <th className="border-b border-line/12 px-4 py-3 font-semibold">Athena</th>
                  <th className="border-b border-line/12 px-4 py-3 font-semibold">
                    Typical agent framework
                  </th>
                </tr>
              </thead>
              <tbody>
                {comparison.map(([label, us, them]) => (
                  <tr key={label}>
                    <td className="border-b border-line/10 px-4 py-3 text-muted">{label}</td>
                    <td className="border-b border-line/10 px-4 py-3 font-medium text-accent">
                      <Check className="mr-1.5 inline h-3.5 w-3.5" />
                      {us}
                    </td>
                    <td className="border-b border-line/10 px-4 py-3 text-muted">{them}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Self-improvement proof */}
      <section className="border-t border-line/10">
        <div className="mx-auto grid max-w-content items-center gap-10 px-6 py-24 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
              The self-evolving harness
            </p>
            <h2 className="mt-3 text-[clamp(26px,3.6vw,34px)] font-semibold tracking-tight">
              It improves itself — and can prove it
            </h2>
            <p className="mt-4 text-muted">
              The harness learns from task outcomes: better routing, per-specialist budgets, prompt
              lessons, distilled playbooks, and promoting proven tools. Above, it has lifted its own
              routing accuracy to 95% over 71 episodes.
            </p>
            <ul className="mt-5 space-y-2.5 text-sm text-muted">
              {[
                "Gated — applied only when the evidence supports it",
                "Signed — written to the ledger as EVOLVE_HARNESS",
                "Reversible — one command undoes it",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2.5">
                  <Check className="mt-0.5 h-4 w-4 flex-none text-accent" />
                  {t}
                </li>
              ))}
            </ul>
            <Link
              href="/docs/self-evolution"
              className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
            >
              How it works <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="overflow-hidden rounded-2xl border border-line/12 shadow-xl shadow-black/30">
            <Image
              src="/images/evolution.png"
              alt="The self-evolving harness"
              width={2400}
              height={2000}
              className="w-full"
            />
          </div>
        </div>
      </section>

      {/* Docs */}
      <section className="border-t border-line/10">
        <div className="mx-auto max-w-content px-6 py-24">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Documentation</p>
          <h2 className="mt-3 text-[clamp(26px,3.6vw,34px)] font-semibold tracking-tight">Learn Athena</h2>
          <div className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {docLinks.map(([title, sub, href]) => (
              <Link
                key={href}
                href={href}
                className="glass rounded-xl px-5 py-4 transition hover:border-accent/35 hover:bg-surface/85"
              >
                <div className="font-semibold text-fg">{title}</div>
                <div className="mt-1 text-[13px] text-faint">{sub}</div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
