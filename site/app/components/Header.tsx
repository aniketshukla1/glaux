import Link from "next/link";
import { Github } from "lucide-react";
import { Logo } from "./Logo";

const REPO = "https://github.com/athena-swarm/athena";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/10 bg-bg/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-content items-center gap-2 px-6 py-3.5">
        <Link href="/" className="flex items-center gap-2 font-semibold text-fg">
          <Logo size={26} /> Athena
        </Link>
        <nav className="ml-auto flex items-center gap-4 text-sm text-muted sm:gap-6">
          <Link href="/#different" className="hidden transition hover:text-fg sm:inline">
            Why Athena
          </Link>
          <Link href="/docs/getting-started" className="transition hover:text-fg">
            Docs
          </Link>
          <a
            href={REPO}
            className="inline-flex items-center gap-1.5 transition hover:text-fg"
            target="_blank"
            rel="noreferrer"
          >
            <Github className="h-4 w-4" /> GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
