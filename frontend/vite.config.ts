import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-time proxy to the Django backend — avoids needing CORS headers
// (django-cors-headers isn't in CLAUDE.md §9's approved dependency list)
// during local development. Production serving (same-origin via a reverse
// proxy, or Django serving the built assets) is a deployment decision left
// for later.
//
// The proxy target is configurable via VITE_API_PROXY_TARGET because it
// differs between running `npm run dev` directly on the host
// (localhost:8001, matching docker-compose's remapped web port) and running
// inside docker-compose's own frontend service (http://web:8000, the
// in-network service name/port — "localhost" inside that container means
// the container itself, not the host or the web service).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      host: true, // bind 0.0.0.0 so it's reachable from outside a container
      proxy: {
        '/api': env.VITE_API_PROXY_TARGET || 'http://localhost:8001',
      },
    },
  }
})
