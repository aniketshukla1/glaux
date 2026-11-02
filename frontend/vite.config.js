import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api and /ws to the FastAPI backend
// (PYTHONPATH=src uvicorn core.api:app --port 8000). Override with
// GLAUX_DEV_PORT / GLAUX_API to run a second instance side by side (the
// pre-rename ATHENA_* names still work).
const env = (name) => process.env[`GLAUX_${name}`] || process.env[`ATHENA_${name}`]
const api = env('API') || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(env('DEV_PORT')) || 5174,
    proxy: {
      '/api': api,
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
})
