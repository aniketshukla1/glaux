import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api and /ws to the FastAPI backend
// (PYTHONPATH=src uvicorn core.api:app --port 8000). Override with
// ATHENA_DEV_PORT / ATHENA_API to run a second instance side by side.
const api = process.env.ATHENA_API || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.ATHENA_DEV_PORT) || 5174,
    proxy: {
      '/api': api,
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
})
