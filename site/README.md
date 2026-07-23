# Athena website

The marketing landing page and documentation, as a **Next.js 14 (App Router)** app with
Tailwind. It's a static export (`output: "export"`), so it deploys to Vercel, Netlify, or
GitHub Pages alike.

The documentation is generated from the canonical markdown in the repo's `docs/`
directory — that's the source of truth, and it stays readable on GitHub.

## Develop

```bash
cd site
npm install
npm run dev          # http://localhost:3000
```

## Build

```bash
python ../scripts/build_site_docs.py   # docs/*.md -> app/docs/*/page.tsx
npm run build                          # static export to ./out
```

`npm run build` alone is enough if the generated `app/docs/*` pages are already up to
date; re-run the Python step after editing anything in `docs/`.

## Deploy

- **Vercel** (recommended): import the repo and set **Root Directory → `site`**. Next.js
  is auto-detected; no extra config.
- **Netlify**: uses `netlify.toml` at the repo root (base `site`, publish `site/out`).
- **GitHub Pages**: `.github/workflows/pages.yml` builds with
  `NEXT_PUBLIC_BASE_PATH=/athena` and publishes `site/out`.

A custom domain or Vercel wants `basePath` at root (the default). A GitHub Pages *project*
site is served under `/athena`, so the workflow sets `NEXT_PUBLIC_BASE_PATH` accordingly.
