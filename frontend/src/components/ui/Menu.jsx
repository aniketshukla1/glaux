import React, { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { Check } from 'lucide-react'

// A small accessible dropdown: a trigger button plus a popover of menu items.
// Closes on outside click and Escape (returning focus to the trigger); arrow
// keys move between items. Positioned absolutely against the wrapper, so it
// needs no portal for the toolbars it lives in.

const MenuCtx = createContext({ close: () => {} })

export function Menu({ trigger, children, align = 'start', side = 'bottom', width = 'w-56', className = '', onOpenChange }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const btnRef = useRef(null)
  const listRef = useRef(null)
  const id = useId()
  useEffect(() => { onOpenChange?.(open) }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const close = useCallback((refocus = true) => {
    setOpen(false)
    if (refocus) requestAnimationFrame(() => btnRef.current?.focus())
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); close() }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const items = [...(listRef.current?.querySelectorAll('[role="menuitem"]:not([disabled])') || [])]
        if (!items.length) return
        e.preventDefault()
        const i = items.indexOf(document.activeElement)
        const next = e.key === 'ArrowDown' ? (i + 1) % items.length : (i - 1 + items.length) % items.length
        items[i < 0 ? 0 : next].focus()
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey, true)
    // focus the first item so keyboard users land inside the menu
    requestAnimationFrame(() => listRef.current?.querySelector('[role="menuitem"]')?.focus())
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey, true) }
  }, [open, close])

  const pos = [
    side === 'bottom' ? 'top-full mt-1.5' : 'bottom-full mb-1.5',
    align === 'end' ? 'right-0' : 'left-0',
  ].join(' ')

  return (
    <div className={`relative ${className}`} ref={wrapRef}>
      {trigger({
        ref: btnRef,
        onClick: () => setOpen((v) => !v),
        'aria-haspopup': 'menu',
        'aria-expanded': open,
        'aria-controls': open ? id : undefined,
        open,
      })}
      {open && (
        <MenuCtx.Provider value={{ close }}>
          <div id={id} ref={listRef} role="menu"
            className={`absolute ${pos} ${width} popover p-1 z-50 animate-pop-in origin-top`}>
            {children}
          </div>
        </MenuCtx.Provider>
      )}
    </div>
  )
}

export function MenuItem({ icon: Icon, children, onSelect, hint, checked, danger, disabled }) {
  const { close } = useContext(MenuCtx)
  return (
    <button type="button" role="menuitem" disabled={disabled}
      onClick={() => { close(false); onSelect?.() }}
      className={`menu-item focus-visible:outline-none focus-visible:bg-line/10 focus-visible:text-fg disabled:opacity-40 ${danger ? '!text-bad hover:!bg-bad/10' : ''}`}>
      {checked !== undefined
        ? <Check className={`w-3.5 h-3.5 shrink-0 ${checked ? 'text-accent' : 'opacity-0'}`} />
        : Icon && <Icon className="w-3.5 h-3.5 shrink-0" />}
      <span className="flex-1 min-w-0 truncate">{children}</span>
      {hint && <span className="text-faint text-[11px] shrink-0">{hint}</span>}
    </button>
  )
}

export function MenuLabel({ children }) {
  return <div className="px-2 pt-1.5 pb-1 eyebrow">{children}</div>
}

export function MenuSeparator() {
  return <div className="my-1 h-px bg-line/10" role="separator" />
}
