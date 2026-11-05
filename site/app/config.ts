// Deploy-target config. Root ("") for Vercel/Netlify/a custom domain; "/glaux" for a
// GitHub Pages *project* site (set via NEXT_PUBLIC_BASE_PATH in the Pages workflow).
export const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

// Absolute site origin (with any base path), for og:image / sitemap / robots.
export const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://aniketshukla1.github.io/glaux";

// Prefix a public asset so it resolves under the deploy's base path.
export const asset = (p: string) => `${BASE}${p}`;
