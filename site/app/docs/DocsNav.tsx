"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: [string, string][] = [
  ["/docs/getting-started", "Getting started"],
  ["/docs/architecture", "Architecture"],
  ["/docs/self-evolution", "Self-evolving harness"],
  ["/docs/cli", "CLI reference"],
  ["/docs/api", "HTTP API"],
  ["/docs/configuration", "Configuration"],
  ["/docs/security", "Security model"],
];

export function DocsNav() {
  const path = usePathname().replace(/\/$/, "");
  return (
    <nav className="space-y-0.5 text-[14.5px]">
      {NAV.map(([href, label]) => {
        const active = path === href;
        return (
          <Link
            key={href}
            href={href}
            className={`block rounded-lg px-3 py-1.5 transition ${
              active ? "bg-accent/13 text-accent" : "text-muted hover:bg-line/7 hover:text-fg"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
