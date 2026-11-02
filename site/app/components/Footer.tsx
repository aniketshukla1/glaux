import Link from "next/link";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-line/10 py-12">
      <div className="mx-auto flex max-w-content flex-wrap items-center gap-x-6 gap-y-3 px-6 text-sm text-faint">
        <span className="flex items-center gap-2 text-muted">
          <Logo size={22} /> Glaux
        </span>
        <span>1.0.0 · Apache-2.0</span>
        <nav className="ml-auto flex gap-5">
          <Link href="/docs/getting-started" className="transition hover:text-fg">
            Docs
          </Link>
          <a href="https://github.com/athena-swarm/athena" className="transition hover:text-fg" target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a
            href="https://github.com/athena-swarm/athena/blob/main/SECURITY.md"
            className="transition hover:text-fg"
            target="_blank"
            rel="noreferrer"
          >
            Security
          </a>
        </nav>
      </div>
    </footer>
  );
}
