import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import {
  AlarmClock,
  BellRing,
  CalendarClock,
  CheckCircle2,
  FileDown,
  Flag,
  Landmark,
  Lightbulb,
} from 'lucide-react'
import { api, type ChaseQueueItem, type DashboardSummary, type DashItem } from '../api'
import { Badge, Button, Card, EmptyState, fmtDate, fmtDateTime, PageHeader, priorityTone, Spinner, StatusBadge } from '../components/ui'
import { RiskChainsCard } from '../components/RiskChains'

function exportPdf() {
  const original = document.title
  document.title = `Fulcrum brief ${new Date().toISOString().slice(0, 10)}`
  window.print()
  document.title = original
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  const tones: Record<string, string> = {
    red: 'text-rose-600 dark:text-rose-400',
    amber: 'text-amber-600 dark:text-amber-400',
    blue: 'text-sky-600 dark:text-sky-400',
    indigo: 'text-indigo-600 dark:text-indigo-400',
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className={`text-2xl font-bold ${tones[tone]}`}>{value}</div>
      <div className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</div>
    </div>
  )
}

function ItemRow({ item, kind }: { item: DashItem; kind: 'action' | 'commitment' }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium">{item.title}</div>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {item.owner ?? 'Unowned'}
          {item.workstream ? ` · ${item.workstream}` : ''}
          {kind === 'commitment' && item.origin ? ` · from ${item.origin}` : ''}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Badge tone={priorityTone[item.priority]}>{item.priority}</Badge>
        <Badge tone="red">{fmtDate(item.due_date)}</Badge>
      </div>
    </div>
  )
}

function ChaseRow({ item }: { item: ChaseQueueItem }) {
  const queryClient = useQueryClient()
  const chased = useMutation({
    mutationFn: (days: number) => {
      const today = new Date()
      const next = new Date(today.getTime() + days * 86400000)
      return api.post('/chases', {
        [item.item_type === 'action' ? 'action_id' : 'commitment_id']: item.item_id,
        chased_on: today.toISOString().slice(0, 10),
        method: 'chat',
        note: 'Chased from dashboard',
        next_chase_on: next.toISOString().slice(0, 10),
      })
    },
    onSuccess: () => {
      toast.success('Chase logged')
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium">{item.title}</div>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {item.owner_name ?? 'Unowned'} · last chased {fmtDate(item.last_chased_on)}
          {item.days_overdue_chase > 0 && (
            <span className="text-rose-500"> · {item.days_overdue_chase}d overdue</span>
          )}
        </div>
      </div>
      <div className="no-print flex shrink-0 gap-1">
        <Button size="sm" variant="secondary" onClick={() => chased.mutate(2)} title="Chased — remind me again in 2 days">
          +2d
        </Button>
        <Button size="sm" variant="secondary" onClick={() => chased.mutate(7)} title="Chased — remind me again in 7 days">
          +7d
        </Button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get<DashboardSummary>('/dashboard/summary'),
  })

  if (isLoading || !data) return <Spinner />

  const overdue = [...data.overdue_commitments.map((c) => ({ ...c, kind: 'commitment' as const })), ...data.overdue_actions.map((a) => ({ ...a, kind: 'action' as const }))]
  const dueSoon = [...data.due_soon_commitments.map((c) => ({ ...c, kind: 'commitment' as const })), ...data.due_soon_actions.map((a) => ({ ...a, kind: 'action' as const }))]

  const todayLong = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

  return (
    <div className="dashboard-print">
      {/* print-only brief header */}
      <div className="mb-4 hidden border-b-2 border-slate-800 pb-2 print:block">
        <h1 className="text-xl font-bold">Fulcrum — daily brief</h1>
        <p className="text-sm text-slate-600">{todayLong}</p>
      </div>
      <div className="print:hidden">
        <PageHeader
          title="Today"
          subtitle={todayLong}
          actions={
            <Button variant="secondary" onClick={exportPdf} title="Opens the print dialog — choose 'Save as PDF' for a clean daily brief">
              <FileDown size={15} /> Export PDF
            </Button>
          }
        />
      </div>
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4 print:grid-cols-4">
        <Stat label="Overdue items" value={overdue.length} tone="red" />
        <Stat label="Due in 7 days" value={dueSoon.length} tone="amber" />
        <Stat label="Chases due" value={data.chase_queue.length} tone="blue" />
        <Stat label="Decisions waiting" value={data.decision_ready.length} tone="indigo" />
      </div>

      <div className="grid gap-4 xl:grid-cols-2 print:grid-cols-2 print:gap-3">
        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-1.5"><BellRing size={14} /> Chase queue</span>}>
            {data.chase_queue.length === 0 ? (
              <EmptyState icon={<CheckCircle2 size={28} />} title="Nobody needs a nudge" hint="Log a chase on any action or commitment and set a re-chase date to build the queue." />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.chase_queue.map((item) => (
                  <ChaseRow key={`${item.item_type}-${item.item_id}`} item={item} />
                ))}
              </div>
            )}
          </Card>

          <Card title={<span className="flex items-center gap-1.5"><AlarmClock size={14} /> Overdue</span>}>
            {overdue.length === 0 ? (
              <EmptyState icon={<CheckCircle2 size={28} />} title="Nothing overdue" />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {overdue.map((item) => (
                  <ItemRow key={`${item.kind}-${item.id}`} item={item} kind={item.kind} />
                ))}
              </div>
            )}
          </Card>

          <Card title={<span className="flex items-center gap-1.5"><CalendarClock size={14} /> Due in the next 7 days</span>}>
            {dueSoon.length === 0 ? (
              <EmptyState title="Nothing due this week" />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {dueSoon.map((item) => (
                  <ItemRow key={`${item.kind}-${item.id}`} item={item} kind={item.kind} />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-1.5"><Landmark size={14} /> Upcoming meetings</span>}>
            {data.meetings.length === 0 ? (
              <EmptyState title="No meetings in the next fortnight" hint="Create forums and meetings from the Meetings page." />
            ) : (
              <div className="space-y-2.5">
                {data.meetings.map((m) => (
                  <Link key={m.id} to={`/meetings/${m.id}`} className="block rounded-lg border border-slate-100 p-3 transition-colors hover:border-indigo-300 dark:border-slate-800 dark:hover:border-indigo-700">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: m.colour }} />
                        <span className="text-[13px] font-semibold">{m.forum}</span>
                        {m.needs_review && <Badge tone="amber">moved — review</Badge>}
                      </div>
                      <StatusBadge status={m.status} />
                    </div>
                    <div className="mt-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span>{fmtDateTime(m.scheduled_at)}</span>
                      <span>
                        {m.agenda_count} items · {m.allocated_minutes}/{m.capacity_minutes} min
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className={`h-full rounded-full ${m.allocated_minutes > m.capacity_minutes ? 'bg-rose-500' : 'bg-indigo-500'}`}
                        style={{ width: `${Math.min(100, (m.allocated_minutes / m.capacity_minutes) * 100)}%` }}
                      />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Card>

          <Card title={<span className="flex items-center gap-1.5"><Flag size={14} /> Key dates — next 30 days</span>}>
            {data.key_dates.length === 0 ? (
              <EmptyState title="No key dates on the horizon" hint="Add external deadlines and board dates from the Planner page." />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.key_dates.map((kd) => (
                  <div key={kd.id} className="flex items-center justify-between gap-2 py-1.5">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">{kd.title}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {kd.kind.replace('_', ' ')}
                        {kd.workstream ? ` · ${kd.workstream}` : ''}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {kd.hard && <Badge tone="red">hard</Badge>}
                      <Badge tone={kd.days_away <= 7 ? 'amber' : 'slate'}>
                        {kd.days_away === 0 ? 'today' : `${kd.days_away}d`} · {fmtDate(kd.date)}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title={<span className="flex items-center gap-1.5"><Lightbulb size={14} /> Decision-ready, no slot yet</span>}>
            {data.decision_ready.length === 0 ? (
              <EmptyState title="No decisions waiting for airtime" />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.decision_ready.map((t) => (
                  <div key={t.id} className="flex items-center justify-between gap-2 py-1.5">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">{t.title}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {t.sponsor ?? 'No sponsor'} · {t.duration_minutes} min
                      </div>
                    </div>
                    {t.target_by && <Badge tone="amber">by {fmtDate(t.target_by)}</Badge>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      <RiskChainsCard className="mt-4" />
    </div>
  )
}
