import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Flag, Plus } from 'lucide-react'
import { api, type KeyDate, type TimelineData, type Workstream } from '../api'
import { RiskChainsCard } from '../components/RiskChains'
import { CapacityHeatmap } from '../components/CapacityHeatmap'
import {
  Badge,
  Button,
  Card,
  cn,
  EmptyState,
  Field,
  fmtDate,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from '../components/ui'

const statusColour: Record<string, string> = {
  open: '#94a3b8',
  on_track: '#10b981',
  at_risk: '#ef4444',
  delivered: '#10b981',
}

export default function Planner() {
  const [weeks, setWeeks] = useState(8)
  const [addingKeyDate, setAddingKeyDate] = useState(false)

  const { data: timeline, isLoading } = useQuery({
    queryKey: ['timeline', weeks],
    queryFn: () => api.get<TimelineData>(`/planner/timeline?weeks=${weeks}`),
  })
  const { data: workstreams = [] } = useQuery({ queryKey: ['workstreams'], queryFn: () => api.get<Workstream[]>('/workstreams') })

  if (isLoading || !timeline) return <Spinner />

  const start = new Date(timeline.from).getTime()
  const end = new Date(timeline.to).getTime()
  const span = end - start
  const pct = (iso: string) => Math.max(0, Math.min(100, ((new Date(iso).getTime() - start) / span) * 100))
  const weekMarks = Array.from({ length: weeks }, (_, i) => {
    const d = new Date(start + i * 7 * 86400000)
    return { pct: ((i * 7 * 86400000) / span) * 100, label: d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) }
  })

  return (
    <div>
      <PageHeader
        title="Forward planner"
        subtitle="Every moving part on one timeline — commitments, hard dates, meetings, and what's at risk"
        actions={
          <>
            <Select value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} className="!w-32">
              <option value={4}>4 weeks</option>
              <option value={8}>8 weeks</option>
              <option value={12}>12 weeks</option>
            </Select>
            <Button onClick={() => setAddingKeyDate(true)}>
              <Plus size={15} /> Key date
            </Button>
          </>
        }
      />

      <Card className="mb-4 overflow-x-auto">
        <div className="min-w-[700px]">
          {/* week ruler */}
          <div className="relative mb-1 ml-44 h-5 border-b border-slate-200 dark:border-slate-700">
            {weekMarks.map((mark) => (
              <span key={mark.pct} className="absolute -translate-x-1/2 text-[10px] text-slate-400" style={{ left: `${mark.pct}%` }}>
                {mark.label}
              </span>
            ))}
          </div>

          {/* meetings track */}
          <div className="mb-2 flex items-center">
            <div className="w-44 shrink-0 pr-3 text-right text-xs font-semibold text-slate-500">Meetings</div>
            <div className="relative h-7 flex-1 rounded-md bg-slate-50 dark:bg-slate-800/40">
              <TodayLine pct={pct(new Date().toISOString())} />
              {timeline.meetings.map((m) => (
                <span
                  key={m.id}
                  title={`${m.forum} — ${new Date(m.scheduled_at).toLocaleString('en-GB')}`}
                  className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-white shadow-sm dark:border-slate-900"
                  style={{ left: `${pct(m.scheduled_at)}%`, background: m.colour }}
                />
              ))}
            </div>
          </div>

          {/* workstream lanes */}
          {timeline.lanes.map((lane, laneIndex) => (
            <div key={lane.workstream?.id ?? `un-${laneIndex}`} className="mb-1.5 flex items-center">
              <div className="w-44 shrink-0 pr-3 text-right">
                <span className="inline-flex items-center gap-1.5 text-xs font-medium">
                  {lane.workstream && <span className="h-2 w-2 rounded-full" style={{ background: lane.workstream.colour }} />}
                  {lane.workstream?.name ?? 'Unassigned'}
                </span>
              </div>
              <div className="relative h-9 flex-1 overflow-hidden rounded-md bg-slate-50 dark:bg-slate-800/40">
                <TodayLine pct={pct(new Date().toISOString())} />
                {weekMarks.map((mark) => (
                  <span key={mark.pct} className="absolute top-0 bottom-0 border-l border-slate-100 dark:border-slate-800" style={{ left: `${mark.pct}%` }} />
                ))}
                {lane.commitments.map((c) => (
                  <span
                    key={c.id}
                    title={`${c.title}\nOwner: ${c.owner ?? '—'} · due ${fmtDate(c.due_date)} · ${c.status}`}
                    className="absolute top-1/2 flex h-5 max-w-[45%] -translate-x-1/2 -translate-y-1/2 items-center truncate rounded-full border border-white px-2 text-[10px] font-medium text-white shadow-sm dark:border-slate-900"
                    style={{ left: `${pct(c.due_date)}%`, background: statusColour[c.status] ?? '#94a3b8' }}
                  >
                    {c.title}
                  </span>
                ))}
                {lane.key_dates.map((kd) => (
                  <span
                    key={kd.id}
                    title={`${kd.title} — ${fmtDate(kd.date)}${kd.hard ? ' (hard)' : ''}`}
                    className="absolute top-0.5 -translate-x-1/2"
                    style={{ left: `${pct(kd.date)}%` }}
                  >
                    <Flag size={12} className={kd.hard ? 'fill-rose-500 text-rose-500' : 'text-slate-400'} />
                  </span>
                ))}
              </div>
            </div>
          ))}
          {timeline.lanes.length === 0 && (
            <EmptyState title="Nothing on the horizon" hint="Add workstreams, dated commitments and key dates to build the picture." />
          )}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <RiskChainsCard />
        <LookAhead timeline={timeline} />
      </div>

      <CapacityHeatmap weeks={weeks} />
      <KeyDatesCard />
      <AddKeyDateModal open={addingKeyDate} onClose={() => setAddingKeyDate(false)} workstreams={workstreams} />
    </div>
  )
}

function TodayLine({ pct }: { pct: number }) {
  return <span className="absolute top-0 bottom-0 z-10 border-l-2 border-indigo-400/70" style={{ left: `${pct}%` }} title="Today" />
}

function LookAhead({ timeline }: { timeline: TimelineData }) {
  const weeksData = useMemo(() => {
    const buckets = new Map<string, { label: string; items: { text: string; tone: string }[] }>()
    const weekKey = (iso: string) => {
      const d = new Date(iso)
      const monday = new Date(d.getTime() - ((d.getDay() + 6) % 7) * 86400000)
      const key = monday.toISOString().slice(0, 10)
      return { key, label: `w/c ${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}` }
    }
    const push = (iso: string, text: string, tone: string) => {
      const { key, label } = weekKey(iso)
      if (!buckets.has(key)) buckets.set(key, { label, items: [] })
      buckets.get(key)!.items.push({ text, tone })
    }
    for (const lane of timeline.lanes) {
      const ws = lane.workstream?.name
      for (const c of lane.commitments) push(c.due_date, `${c.title} due${ws ? ` (${ws})` : ''}`, c.status === 'at_risk' ? 'red' : 'slate')
      for (const kd of lane.key_dates) push(kd.date, `⚑ ${kd.title}`, kd.hard ? 'red' : 'amber')
    }
    for (const m of timeline.meetings) push(m.scheduled_at, `${m.forum}`, 'blue')
    return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [timeline])

  return (
    <Card title="Week-by-week look-ahead">
      {weeksData.length === 0 ? (
        <EmptyState title="Nothing scheduled in this window" />
      ) : (
        <div className="max-h-96 space-y-3 overflow-y-auto pr-1">
          {weeksData.map(([key, week]) => (
            <div key={key}>
              <div className="mb-1 text-xs font-bold text-slate-500 dark:text-slate-400">{week.label}</div>
              <ul className="space-y-1">
                {week.items.map((item, i) => (
                  <li key={i} className="flex items-center gap-1.5 text-[13px]">
                    <span
                      className={cn(
                        'h-1.5 w-1.5 shrink-0 rounded-full',
                        item.tone === 'red' && 'bg-rose-500',
                        item.tone === 'amber' && 'bg-amber-500',
                        item.tone === 'blue' && 'bg-sky-500',
                        item.tone === 'slate' && 'bg-slate-400',
                      )}
                    />
                    {item.text}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function KeyDatesCard() {
  const queryClient = useQueryClient()
  const { data: keyDates = [] } = useQuery({ queryKey: ['key-dates'], queryFn: () => api.get<KeyDate[]>('/key-dates') })
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/key-dates/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['key-dates'] })
      queryClient.invalidateQueries({ queryKey: ['timeline'] })
    },
  })
  return (
    <Card title="All key dates" className="mt-4">
      {keyDates.length === 0 ? (
        <EmptyState title="No key dates recorded" hint="External deadlines, regulator submissions, board and committee dates." />
      ) : (
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800">
              <th className="py-2 pr-3 font-medium">Date</th>
              <th className="py-2 pr-3 font-medium">Title</th>
              <th className="py-2 pr-3 font-medium">Kind</th>
              <th className="py-2 pr-3 font-medium">Workstream</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50 dark:divide-slate-800/60">
            {keyDates.map((kd) => (
              <tr key={kd.id}>
                <td className="py-2 pr-3 whitespace-nowrap">
                  <Badge tone={kd.hard ? 'red' : 'slate'}>{fmtDate(kd.date, { day: 'numeric', month: 'short', year: 'numeric' })}</Badge>
                </td>
                <td className="py-2 pr-3 font-medium">{kd.title}</td>
                <td className="py-2 pr-3">{kd.kind.replace('_', ' ')}</td>
                <td className="py-2 pr-3">{kd.workstream?.name ?? '—'}</td>
                <td className="py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => remove.mutate(kd.id)}>
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function AddKeyDateModal({ open, onClose, workstreams }: { open: boolean; onClose: () => void; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))
  const create = useMutation({
    mutationFn: () =>
      api.post('/key-dates', {
        title: form.title,
        date: form.date,
        kind: form.kind || 'internal',
        hard: form.hard === 'true',
        workstream_id: form.workstream_id ? Number(form.workstream_id) : null,
        notes: form.notes || null,
      }),
    onSuccess: () => {
      toast.success('Key date added')
      setForm({})
      onClose()
      queryClient.invalidateQueries({ queryKey: ['key-dates'] })
      queryClient.invalidateQueries({ queryKey: ['timeline'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Modal open={open} onClose={onClose} title="New key date">
      <div className="space-y-3">
        <Field label="Title">
          <Input value={form.title ?? ''} onChange={set('title')} autoFocus placeholder="e.g. PRA submission deadline" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date">
            <Input type="date" value={form.date ?? ''} onChange={set('date')} />
          </Field>
          <Field label="Kind">
            <Select value={form.kind ?? 'internal'} onChange={set('kind')}>
              <option value="external_deadline">external deadline</option>
              <option value="regulator">regulator</option>
              <option value="board">board / committee</option>
              <option value="internal">internal</option>
            </Select>
          </Field>
          <Field label="Hard deadline?">
            <Select value={form.hard ?? 'false'} onChange={set('hard')}>
              <option value="false">No — movable</option>
              <option value="true">Yes — immovable</option>
            </Select>
          </Field>
          <Field label="Workstream">
            <Select value={form.workstream_id ?? ''} onChange={set('workstream_id')}>
              <option value="">None</option>
              {workstreams.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Notes">
          <Textarea rows={2} value={form.notes ?? ''} onChange={set('notes')} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!form.title || !form.date} onClick={() => create.mutate()}>
            Add
          </Button>
        </div>
      </div>
    </Modal>
  )
}
