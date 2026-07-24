import Link from "next/link";
import { Logo } from "./components/Logo";

export const metadata = { title: "Not found — Athena" };

export default function NotFound() {
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <div className="drop-shadow-[0_0_20px_rgb(var(--accent)/0.4)]">
        <Logo size={56} />
      </div>
      <h1 className="mt-6 text-4xl font-semibold tracking-tight text-fg">Page not found</h1>
      <p className="mt-3 max-w-md text-muted">
        That page isn&apos;t here — but the ledger still verifies. Try the docs or head home.
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-3">
        <Link
          href="/"
          className="rounded-xl bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-medium text-[#04121a] transition hover:brightness-110"
        >
          Back home
        </Link>
        <Link
          href="/docs"
          className="rounded-xl border border-line/20 px-5 py-2.5 text-sm font-medium text-fg transition hover:border-line/40 hover:bg-line/5"
        >
          Documentation
        </Link>
      </div>
    </main>
  );
}
