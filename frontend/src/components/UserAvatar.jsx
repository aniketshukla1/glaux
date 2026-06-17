import React from 'react'
import { initials, avatarColor } from '../lib/avatar.js'

export default function UserAvatar({ user, size = 32, className = '' }) {
  if (!user) return null
  return (
    <div
      className={`rounded-full grid place-items-center font-semibold text-white shrink-0 ${className}`}
      style={{ width: size, height: size, background: avatarColor(user.id || user.email), fontSize: size * 0.4 }}
      title={user.name || user.email}
    >
      {initials(user.name, user.email)}
    </div>
  )
}
