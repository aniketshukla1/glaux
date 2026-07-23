export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="athena-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="rgb(45,212,191)" />
          <stop offset="1" stopColor="rgb(129,140,248)" />
        </linearGradient>
      </defs>
      <circle cx="23" cy="34" r="11" stroke="url(#athena-mark)" strokeWidth="3.4" />
      <circle cx="41" cy="34" r="11" stroke="url(#athena-mark)" strokeWidth="3.4" />
      <circle cx="23" cy="34" r="3.6" fill="url(#athena-mark)" />
      <circle cx="41" cy="34" r="3.6" fill="url(#athena-mark)" />
      <path d="M14 20l7 6M50 20l-7 6" stroke="url(#athena-mark)" strokeWidth="3.4" strokeLinecap="round" />
    </svg>
  );
}
