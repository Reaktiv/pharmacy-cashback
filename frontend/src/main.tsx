import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from './api/client'
import './index.css'
import App from './App.tsx'

// Global defaults for every useQuery in the app. staleTime keeps fetched
// data fresh-enough for a normal editing session without every page nav
// re-triggering a request; refetchOnWindowFocus is off because this is an
// internal admin tool (tab-switching to check something else shouldn't
// spam refetches), not a live feed that needs to catch up instantly.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      // A 401 here means apiFetch already tried its one refresh-token
      // retry (api/client.ts) and it failed — endSession() has cleared
      // both tokens, so every further attempt is guaranteed to 401 again
      // too. Retrying is pure network waste, and AuthContext's
      // SESSION_EXPIRED_EVENT listener is already sending the user to
      // /login regardless. Anything else (a dropped connection, a
      // one-off 500) is genuinely transient, so it keeps the default
      // retry behavior.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status === 401) return false
        return failureCount < 3
      },
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
