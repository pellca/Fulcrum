import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BellRing,
  CalendarDays,
  ClipboardList,
  Flag,
  Gavel,
  Landmark,
  Layers,
  Lightbulb,
  Search,
  Target,
  User,
} from 'lucide-react'
import { api } from '../api'
import { cn } from './ui'

interface SearchResult {
  type: string
  id: number | string
  title: string
  url: string
  meta: string | null
  snippet: string | null
}

const TYPE_META: Record<string, { label: string; icon: typeof Search }> = {
  person: { label: 'People', icon: User },
  action: { label: 'Actions', icon: ClipboardList },
  commitment: { label: 'Commitments', icon: Target },
  topic: { label: 'Topics', icon: Lightbulb },
  decision: { label: 'Decisions', icon: Gavel },
  key_date: { label: 'Key dates', icon: Flag },
  workstream: { label: 'Workstreams', icon: Layers },
  forum: { label: 'Forums', icon: Landmark },
  meeting: { label: 'Meetings', icon: Landmark },
  chase: { label: 'Chase notes', icon: BellRing },
  diary_event: { label: 'Diary', icon: CalendarDays },
}

export function GlobalSearch() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 30)
    } else {
      setQuery('')
      setDebounced('')
      setActive(0)
    }
  }, [open])

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 200)
    return () => clearTimeout(timer)
  }, [query])

  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api.get<{ results: SearchResult[] }>(`/search?q=${encodeURIComponent(debounced)}`),
    enabled: debounced.length >= 2,
    placeholderData: (previous) => previous,
  })

  const results = useMemo(() => (debounced.length >= 2 ? (data?.results ?? []) : []), [data, debounced])
  const grouped = useMemo(() => {
    const groups = new Map<string, SearchResult[]>()
    for (const result of results) {
      if (!groups.has(result.type)) groups.set(result.type, [])
      groups.get(result.type)!.push(result)
    }
    return [...groups.entries()]
  }, [results])

  useEffect(() => setActive(0), [results])

  const go = (result: SearchResult) => {
    setOpen(false)
    navigate(result.url)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault()
      go(results[active])
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-[13px] text-slate-400 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:hover:border-slate-500"
        title="Search everything (Ctrl+/)"
      >
        <Search size={14} />
        <span>Search…</span>
        <kbd className="rounded border border-slate-300 px-1 text-[10px] dark:border-slate-600">Ctrl+/</kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 p-4 pt-[12vh] backdrop-blur-sm"
          onMouseDown={() => setOpen(false)}
        >
          <div
            className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 dark:border-slate-800">
              <Search size={15} className="shrink-0 text-slate-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Search actions, commitments, people, decisions, diary, chase notes…"
                className="w-full bg-transparent py-3 text-sm outline-none placeholder:text-slate-400"
              />
              {isFetching && <div className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />}
            </div>

            <div className="max-h-[55vh] overflow-y-auto p-2">
              {debounced.length < 2 ? (
                <p className="px-3 py-6 text-center text-xs text-slate-400">
                  Type at least two characters — results update as you type.
                </p>
              ) : results.length === 0 && !isFetching ? (
                <p className="px-3 py-6 text-center text-xs text-slate-400">No matches for “{debounced}”.</p>
              ) : (
                grouped.map(([type, items]) => {
                  const meta = TYPE_META[type] ?? { label: type, icon: Search }
                  const Icon = meta.icon
                  return (
                    <div key={type} className="mb-1">
                      <div className="px-3 py-1 text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                        {meta.label}
                      </div>
                      {items.map((result) => {
                        const index = results.indexOf(result)
                        return (
                          <button
                            key={`${result.type}-${result.id}`}
                            onClick={() => go(result)}
                            onMouseEnter={() => setActive(index)}
                            className={cn(
                              'flex w-full items-start gap-2.5 rounded-lg px-3 py-2 text-left',
                              index === active && 'bg-indigo-50 dark:bg-indigo-950/50',
                            )}
                          >
                            <Icon size={15} className="mt-0.5 shrink-0 text-slate-400" />
                            <span className="min-w-0">
                              <span className="block truncate text-[13px] font-medium">{result.title}</span>
                              {result.meta && (
                                <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">
                                  {result.meta}
                                </span>
                              )}
                              {result.snippet && (
                                <span className="block truncate text-[11px] text-slate-400 italic">{result.snippet}</span>
                              )}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  )
                })
              )}
            </div>
            <div className="border-t border-slate-100 px-4 py-1.5 text-[10px] text-slate-400 dark:border-slate-800">
              ↑↓ navigate · Enter open · Esc close
            </div>
          </div>
        </div>
      )}
    </>
  )
}
