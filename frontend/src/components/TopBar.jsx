import React from 'react'
import { Menu as MenuIcon } from 'lucide-react'

// Slim, sticky bar above the content. On pages that carry their own title it
// only exists on small screens, to reach the menu.
export default function TopBar({ title, onOpenMobileNav, children }) {
  const bare = !title && !children
  return (
    <header className={`sticky top-0 z-30 h-12 flex items-center gap-2 px-3 sm:px-5 bg-[rgb(var(--bg))]/85 backdrop-blur-md border-b border-line/[0.07] ${bare ? 'md:hidden' : ''}`}>
      <button onClick={onOpenMobileNav} className="md:hidden btn-ghost p-1.5 -ml-1" aria-label="Open menu">
        <MenuIcon className="w-4 h-4" />
      </button>
      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-fg">{title}</span>
      {children && <div className="flex items-center gap-0.5 shrink-0">{children}</div>}
    </header>
  )
}
