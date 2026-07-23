import Link from "next/link";
import { ArrowRight } from "lucide-react";

export const metadata = { title: "Documentation — Athena" };

const DOCS: [string, string, string][] = [
  ["Getting started", "Install, first run, and your first swarm.", "/docs/getting-started"],
  ["Architecture", "The swarm, the ledger, the sandbox, and memory.", "/docs/architecture"],
  ["Self-evolving harness", "How Athena improves its own configuration — safely.", "/docs/self-evolution"],
  ["CLI reference", "Every athena command.", "/docs/cli"],
  ["HTTP API", "The stable endpoint surface.", "/docs/api"],
  ["Configuration", "Models, environment variables, and capabilities.", "/docs/configuration"],
  ["Security model", "The sandbox, the jail, the ledger, and the trade-offs.", "/docs/security"],
];

export default function DocsIndex() {
  return (
    <div className="not-prose">
      <h1 className="text-4xl font-semibold tracking-tight text-fg">Documentation</h1>
      <p className="mt-3 text-muted">Everything you need to run, drive, and understand Athena.</p>
      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {DOCS.map(([title, sub, href]) => (
          <Link
            key={href}
            href={href}
            className="group glass rounded-xl px-5 py-4 transition hover:border-accent/35 hover:bg-surface/85"
          >
            <div className="flex items-center justify-between font-semibold text-fg">
              {title}
              <ArrowRight className="h-4 w-4 text-faint transition group-hover:translate-x-0.5 group-hover:text-accent" />
            </div>
            <div className="mt-1 text-[13px] text-faint">{sub}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
