import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, FileDown } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, EmptyState, fmtDate, priorityTone, Spinner, StatusBadge } from '../components/ui'

interface PackItem {
  id: number
  type: string
  title: string
  due_date: string | null
  status: string
  priority: string
  workstream: string | null
  origin: string | null
  last_chased_on: string | null
  next_chase_on: string | null
}

interface Pack {
  person: { id: number; name: string; role: string | null; team: string | null }
  generated: string
  overdue: PackItem[]
  due_soon: PackItem[]
  later: PackItem[]
  waiting_on: PackItem[]
  decisions: { id: number; title: string; status: string; decided_on: string | null; review_on: string | null }[]
  topics: { id: number; title: string; intent: string; readiness: string; status: string; target_by: string | null; duration_minutes: number }[]
}

function ItemRows({ items, showChase }: { items: PackItem[]; showChase?: boolean }) {
  return (
    <div className="divide-y divide-slate-100 dark:divide-slate-800">
      {items.map((item) => (
        <Link
          key={`${item.type}-${item.id}`}
          to={`/register?open=${item.type}-${item.id}`}
          className="flex items-center justify-between gap-2 py-1.5 hover:bg-indigo-50/40 dark:hover:bg-indigo-950/20"
        >
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium">{item.title}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {item.type}
              {item.workstream ? ` · ${item.workstream}` : ''}
              {item.origin ? ` · from ${item.origin}` : ''}
              {showChase && item.last_chased_on ? ` · last chased ${fmtDate(item.last_chased_on)}` : ''}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Badge tone={priorityTone[item.priority]}>{item.priority}</Badge>
            <StatusBadge status={item.status} />
            <Badge tone="slate">{fmtDate(item.due_date)}</Badge>
          </div>
        </Link>
      ))}
    </div>
  )
}

export default function OneToOnePack() {
  const { id } = useParams()
  const { data: pack, isLoading } = useQuery({
    queryKey: ['pack', id],
    queryFn: () => api.get<Pack>(`/people/${id}/pack`),
  })

  if (isLoading || !pack) return <Spinner />

  const exportPdf = () => {
    const original = document.title
    document.title = `1-1 ${pack.person.name} ${pack.generated}`
    window.print()
    document.title = original
  }

  const empty =
    !pack.overdue.length && !pack.due_soon.length && !pack.later.length && !pack.decisions.length && !pack.topics.length

  return (
    <div className="dashboard-print mx-auto max-w-3xl">
      <div className="no-print mb-3 flex items-center justify-between">
        <Link to="/people" className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-indigo-600">
          <ArrowLeft size={13} /> People
        </Link>
        <Button variant="secondary" onClick={exportPdf}>
          <FileDown size={15} /> Export PDF
        </Button>
      </div>

      <div className="mb-5 border-b-2 border-slate-800 pb-3 dark:border-slate-200 print:border-slate-800">
        <h1 className="text-xl font-bold tracking-tight">1:1 pack — {pack.person.name}</h1>
        <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
          {[pack.person.role, pack.person.team].filter(Boolean).join(' · ')} · prepared{' '}
          {fmtDate(pack.generated, { day: 'numeric', month: 'long', year: 'numeric' })}
        </p>
      </div>

      {empty && <EmptyState title="Nothing open for this person" hint="No open actions, commitments, decisions or topics." />}

      <div className="space-y-4">
        {pack.waiting_on.length > 0 && (
          <Card title={`Waiting on them — chase now (${pack.waiting_on.length})`}>
            <ItemRows items={pack.waiting_on} showChase />
          </Card>
        )}
        {pack.overdue.length > 0 && (
          <Card title={`Overdue (${pack.overdue.length})`}>
            <ItemRows items={pack.overdue} showChase />
          </Card>
        )}
        {pack.due_soon.length > 0 && (
          <Card title={`Due in the next 14 days (${pack.due_soon.length})`}>
            <ItemRows items={pack.due_soon} showChase />
          </Card>
        )}
        {pack.later.length > 0 && (
          <Card title={`Everything else open (${pack.later.length})`}>
            <ItemRows items={pack.later} />
          </Card>
        )}
        {pack.decisions.length > 0 && (
          <Card title={`Decisions they own (${pack.decisions.length})`}>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {pack.decisions.map((decision) => (
                <div key={decision.id} className="flex items-center justify-between gap-2 py-1.5">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-medium">{decision.title}</div>
                    {decision.decided_on && (
                      <div className="text-xs text-slate-500">decided {fmtDate(decision.decided_on)}</div>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <StatusBadge status={decision.status} />
                    {decision.review_on && <Badge tone="amber">review {fmtDate(decision.review_on)}</Badge>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
        {pack.topics.length > 0 && (
          <Card title={`Topics they're sponsoring (${pack.topics.length})`}>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {pack.topics.map((topic) => (
                <div key={topic.id} className="flex items-center justify-between gap-2 py-1.5">
                  <div className="min-w-0 truncate text-[13px] font-medium">{topic.title}</div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Badge tone="indigo">{topic.intent}</Badge>
                    <Badge tone={topic.readiness === 'ready' ? 'green' : 'slate'}>{topic.readiness}</Badge>
                    {topic.target_by && <Badge tone="amber">by {fmtDate(topic.target_by)}</Badge>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
