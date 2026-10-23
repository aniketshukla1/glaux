import React from 'react'

// Shared frame for the top-level pages: a title row, an optional tab strip,
// and a centred content column.
export default function Page({ title, description, actions, tabs, tab, onTab, children, wide }) {
  const active = tabs?.find((t) => t.key === tab)
  return (
    <div className={`w-full ${wide ? 'max-w-5xl' : 'max-w-4xl'} mx-auto px-5 sm:px-8 pt-6 pb-16`}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-fg text-[20px] font-semibold tracking-tight">{title}</h1>
          {description && <p className="text-muted text-[13px] mt-1 max-w-2xl leading-relaxed">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {tabs && (
        <div role="tablist" aria-label={`${title} sections`}
          className="mt-5 -mx-1 flex gap-0.5 border-b border-line/[0.08] overflow-x-auto overflow-y-hidden">
          {tabs.map((t) => (
            <button key={t.key} role="tab" id={`tab-${t.key}`} aria-selected={tab === t.key} onClick={() => onTab(t.key)}
              className={`relative shrink-0 px-3 py-2 text-[13px] transition-colors ${
                tab === t.key ? 'text-fg font-medium' : 'text-muted hover:text-fg'
              }`}>
              {t.label}
              {t.count > 0 && <span className="ml-1.5 text-[11px] text-faint tabular-nums">{t.count}</span>}
              {tab === t.key && <span className="absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-accent" />}
            </button>
          ))}
        </div>
      )}
      <div className="mt-6" role={tabs ? 'tabpanel' : undefined} aria-labelledby={active ? `tab-${active.key}` : undefined}>
        {active?.hint && <p className="text-faint text-[12.5px] -mt-2 mb-5 max-w-2xl leading-relaxed">{active.hint}</p>}
        {children}
      </div>
    </div>
  )
}
