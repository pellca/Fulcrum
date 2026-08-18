import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'
import './index.css'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Register from './pages/Register'
import Topics from './pages/Topics'
import Meetings from './pages/Meetings'
import MeetingDetail from './pages/MeetingDetail'
import Planner from './pages/Planner'
import Diary from './pages/Diary'
import Mailbox from './pages/Mailbox'
import People from './pages/People'
import OneToOnePack from './pages/OneToOnePack'
import Modules from './pages/Modules'
import SettingsPage from './pages/Settings'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
})

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/register', element: <Register /> },
      { path: '/topics', element: <Topics /> },
      { path: '/meetings', element: <Meetings /> },
      { path: '/meetings/:id', element: <MeetingDetail /> },
      { path: '/planner', element: <Planner /> },
      { path: '/diary', element: <Diary /> },
      { path: '/mailbox', element: <Mailbox /> },
      { path: '/people', element: <People /> },
      { path: '/people/:id/pack', element: <OneToOnePack /> },
      { path: '/modules', element: <Modules /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster richColors position="bottom-right" />
    </QueryClientProvider>
  </StrictMode>,
)
