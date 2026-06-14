import React from 'react'

// The Athena mark — her owl of wisdom, in the brand gradient. Transparent
// background so it sits inside its own chip/container. Tightly bounded viewBox
// so it fills whatever size it's given.
export default function AthenaMark({ className = 'w-6 h-6' }) {
  return (
    <svg viewBox="205 295 610 395" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="athena-mark" gradientUnits="userSpaceOnUse" x1="230" y1="320" x2="790" y2="660">
          <stop offset="0" stopColor="#2dd4bf" />
          <stop offset="0.55" stopColor="#34d399" />
          <stop offset="1" stopColor="#818cf8" />
        </linearGradient>
      </defs>
      <g fill="none" stroke="url(#athena-mark)" strokeWidth="34" strokeLinecap="round" strokeLinejoin="round">
        <path d="M286 408 L232 330" />
        <path d="M738 408 L792 330" />
        <path d="M286 408 Q372 300 512 392 Q652 300 738 408" />
        <circle cx="384" cy="528" r="132" />
        <circle cx="640" cy="528" r="132" />
      </g>
      <circle cx="384" cy="536" r="46" fill="url(#athena-mark)" />
      <circle cx="640" cy="536" r="46" fill="url(#athena-mark)" />
      <path d="M512 542 L556 598 L512 660 L468 598 Z" fill="url(#athena-mark)" />
    </svg>
  )
}
