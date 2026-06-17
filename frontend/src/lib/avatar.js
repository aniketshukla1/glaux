// Deterministic initials + color for a user, so avatars are stable without uploads.
const COLORS = [
  '#2dd4bf', '#38bdf8', '#818cf8', '#f472b6', '#fbbf24',
  '#34d399', '#fb7185', '#a78bfa', '#e879f9', '#60a5fa',
]

export function initials(name, email) {
  const s = (name || email || '?').trim()
  const parts = s.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return s.slice(0, 2).toUpperCase()
}

export function avatarColor(seed) {
  const s = String(seed || '')
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return COLORS[h % COLORS.length]
}
