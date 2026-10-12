import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// API_BASE_URL is the name the family contract uses (docs/architecture.md in
// the parent), so it is exposed to the client alongside Vite's VITE_ prefix.
// VITE_DEV_PROXY=http://localhost:8000 makes the dev server forward /api/* to
// a local gateway or service, so the app runs same-origin like in the cluster
// and API_BASE_URL can stay empty.
const proxyTarget = process.env.VITE_DEV_PROXY

export default defineConfig({
  plugins: [react()],
  server: proxyTarget ? { proxy: { '/api': { target: proxyTarget, changeOrigin: true } } } : undefined,
  envPrefix: ['VITE_', 'API_'],
  build: {
    // markmap (with d3) is loaded on demand by the mind map renderer only;
    // its chunk is large but never part of the initial load.
    chunkSizeWarningLimit: 650,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
