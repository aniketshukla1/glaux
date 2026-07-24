import { DocsNav } from "./DocsNav";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto grid max-w-content grid-cols-1 gap-10 px-6 md:grid-cols-[224px_minmax(0,1fr)]">
      <aside className="hidden py-10 md:block">
        <div className="sticky top-20">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-faint">
            Documentation
          </p>
          <DocsNav />
        </div>
      </aside>
      <article className="prose prose-invert min-w-0 max-w-none py-10 prose-pre:overflow-x-auto prose-headings:scroll-mt-24 prose-h1:text-4xl prose-h1:font-semibold prose-h1:tracking-tight prose-pre:border prose-pre:border-line/12 prose-pre:bg-surface/90 prose-code:before:content-none prose-code:after:content-none prose-a:font-medium prose-a:no-underline hover:prose-a:underline">
        {children}
      </article>
    </div>
  );
}
