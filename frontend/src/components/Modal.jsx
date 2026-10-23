import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'

// A large, centered full-screen card (a bit smaller than the viewport) with a
// blurred backdrop. Portaled to <body> so it sits above the sticky shell, and
// closes on Escape or a backdrop click. Children own the internal layout.
export default function Modal({ open, onClose, className = 'max-w-5xl', label, children }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-3 sm:p-6">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div
        className={`relative card w-full ${className} h-[90vh] max-h-[920px] flex flex-col overflow-hidden shadow-2xl animate-fade-up`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
      >
        {children}
      </div>
    </div>,
    document.body,
  )
}
