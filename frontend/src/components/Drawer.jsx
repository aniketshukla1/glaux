import React from 'react'
import { X } from 'lucide-react'

export default function Drawer({ open, onClose, title, icon, width = 460, dark = false, children }) {
  return (
    <div className={`fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`} {...(dark ? { 'data-theme': 'dark' } : {})}>
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/50 transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}
      />
      <div
        className={`absolute right-0 top-0 h-full bg-bg border-l border-line/12 flex flex-col transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ width: `min(${width}px, 100vw)` }}
      >
        <div className="flex items-center gap-2 px-5 py-4 border-b border-line/10 shrink-0">
          {icon}
          <h2 className="text-fg font-medium">{title}</h2>
          <button onClick={onClose} className="btn p-1.5 ml-auto" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  )
}
