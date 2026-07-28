import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  CalendarDays,
  ClipboardList,
  Gauge,
  Landmark,
  Lightbulb,
  Moon,
  Puzzle,
  Settings,
  Sun,
  TrendingUpDown,
  Users,
} from 'lucide-react'
import { cn } from './ui'
import { QuickAdd } from './QuickAdd'

const nav = [
  { to: '/', label: 'Today', icon: Gauge },
  { to: '/register', label: 'Register', icon: ClipboardList },
  { to: '/topics', label: 'Topics', icon: Lightbulb },
  { to: '/meetings', label: 'Meetings', icon: Landmark },
  { to: '/planner', label: 'Planner', icon: TrendingUpDown },
  { to: '/diary', label: 'Diary', icon: CalendarDays },
  { to: '/people', label: 'People', icon: Users },
  { to: '/modules', label: 'Modules', icon: Puzzle },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function useTheme() {
  const [dark, setDark] = useState(
    () =>
      localStorage.getItem('fulcrum-theme') === 'dark' ||
      (!localStorage.getItem('fulcrum-theme') &&
        window.matchMedia('(prefers-color-scheme: dark)').matches),
  )
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('fulcrum-theme', dark ? 'dark' : 'light')
  }, [dark])
  return { dark, toggle: () => setDark((d) => !d) }
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0">
        <rect width="32" height="32" rx="7" fill="#4f46e5" />
        <path d="M7 22 L16 9 L25 22" stroke="white" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="4" y1="25" x2="28" y2="25" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <div>
        <div className="text-sm leading-none font-bold tracking-tight">Fulcrum</div>
        <div className="mt-0.5 text-[10px] leading-none text-slate-400">Chief of Staff platform</div>
      </div>
    </div>
  )
}

export default function Layout() {
  const { dark, toggle } = useTheme()
  return (
    <div className="flex h-full">
      <aside className="no-print flex w-52 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <Logo />
        <nav className="flex-1 space-y-0.5 px-2">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-2 dark:border-slate-800">
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            {dark ? <Sun size={16} /> : <Moon size={16} />}
            {dark ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print flex items-center justify-end border-b border-slate-200 bg-white px-5 py-2.5 dark:border-slate-800 dark:bg-slate-900">
          <QuickAdd />
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
