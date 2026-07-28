import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Users } from 'lucide-react'
import { api } from '../api'
import { Card, cn, EmptyState } from './ui'

interface Bucket {
  count: number
  items: string[]
}

interface CapacityData {
  weeks: { start: string; label: string }[]
  rows: {
    person: { id: number; name: string; role: string | null }
    overdue: Bucket
    cells: Bucket[]
    no_date: Bucket
    later: Bucket
    total: number
  }[]
}

function Cell({ bucket, tone }: { bucket: Bucket; tone: 'overdue' | 'week' | 'muted' }) {
  const { count } = bucket
  const intensity =
    count === 0
      ? 'bg-slate-50 text-slate-300 dark:bg-slate-800/40 dark:text-slate-600'
      : tone === 'overdue'
        ? 'bg-rose-500 text-white'
        : tone === 'muted'
          ? 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-200'
          : count === 1
            ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300'
            : count === 2
              ? 'bg-indigo-300 text-indigo-950 dark:bg-indigo-800 dark:text-indigo-100'
              : count <= 4
                ? 'bg-indigo-500 text-white'
                : 'bg-indigo-700 text-white'
  return (
    <td className="p-0.5">
      <div
        title={bucket.items.join('\n') || undefined}
        className={cn('flex h-8 min-w-12 items-center justify-center rounded-md text-xs font-semibold', intensity)}
      >
        {count || ''}
      </div>
    </td>
  )
}

export function CapacityHeatmap({ weeks = 8 }: { weeks?: number }) {
  const { data } = useQuery({
    queryKey: ['capacity', weeks],
    queryFn: () => api.get<CapacityData>(`/planner/capacity?weeks=${weeks}`),
  })

  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          <Users size={14} /> Owner capacity — open items by due week
        </span>
      }
      className="mt-4 overflow-x-auto"
    >
      {!data?.rows.length ? (
        <EmptyState title="No owned open items" hint="Assign owners and due dates and the load picture builds itself." />
      ) : (
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr className="text-slate-500 dark:text-slate-400">
              <th className="py-1 pr-2 font-medium">Owner</th>
              <th className="px-0.5 py-1 text-center font-medium text-rose-500">Overdue</th>
              {data.weeks.map((week) => (
                <th key={week.start} className="px-0.5 py-1 text-center font-medium whitespace-nowrap">
                  {week.label}
                </th>
              ))}
              <th className="px-0.5 py-1 text-center font-medium">Later</th>
              <th className="px-0.5 py-1 text-center font-medium">No date</th>
              <th className="px-0.5 py-1 text-center font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.person.id}>
                <td className="max-w-40 py-0.5 pr-2">
                  <Link
                    to={`/register?owner=${row.person.id}`}
                    className="block truncate text-[13px] font-medium hover:text-indigo-600 dark:hover:text-indigo-400"
                    title={row.person.role ?? undefined}
                  >
                    {row.person.name}
                  </Link>
                </td>
                <Cell bucket={row.overdue} tone="overdue" />
                {row.cells.map((cell, index) => (
                  <Cell key={index} bucket={cell} tone="week" />
                ))}
                <Cell bucket={row.later} tone="muted" />
                <Cell bucket={row.no_date} tone="muted" />
                <td className="px-2 text-center font-bold">{row.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-2 text-[11px] text-slate-400">
        Hover a cell for the items behind it · click a name to open their register · darker = heavier load
      </p>
    </Card>
  )
}
