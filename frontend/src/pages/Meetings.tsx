import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { CalendarPlus, Landmark, Plus } from 'lucide-react'
import { api, type Forum, type Meeting, type Person } from '../api'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  fmtDateTime,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
} from '../components/ui'

export default function Meetings() {
  const [showPast, setShowPast] = useState(false)
  const [creatingForum, setCreatingForum] = useState(false)
  const [schedulingFor, setSchedulingFor] = useState<Forum | null>(null)

  const { data: forums, isLoading: loadingForums } = useQuery({ queryKey: ['forums'], queryFn: () => api.get<Forum[]>('/forums') })
  const { data: meetings, isLoading: loadingMeetings } = useQuery({
    queryKey: ['meetings', showPast],
    queryFn: () => api.get<Meeting[]>(`/meetings${showPast ? '' : '?upcoming_only=true'}`),
  })
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })

  if (loadingForums || loadingMeetings) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Meetings"
        subtitle="Your governance forums and their agenda pipeline"
        actions={
          <Button variant="secondary" onClick={() => setCreatingForum(true)}>
            <Plus size={15} /> New forum
          </Button>
        }
      />

      <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(forums ?? []).map((forum) => (
          <Card key={forum.id} className="!shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full" style={{ background: forum.colour }} />
                <div>
                  <div className="text-[13px] font-semibold">{forum.name}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {forum.cadence ?? 'No cadence set'} · {forum.capacity_minutes} min
                    {forum.chair ? ` · chaired by ${forum.chair.name}` : ''}
                  </div>
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setSchedulingFor(forum)} title="Schedule a meeting">
                <CalendarPlus size={15} />
              </Button>
            </div>
          </Card>
        ))}
        {!forums?.length && (
          <div className="md:col-span-2 xl:col-span-3">
            <EmptyState
              icon={<Landmark size={28} />}
              title="No forums yet"
              hint="A forum is a recurring governance meeting with a time budget — AET weekly, Audit Committee prep, 1:1 with your principal."
            />
          </div>
        )}
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Meetings</h2>
        <label className="flex items-center gap-1.5 text-[13px] text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={showPast} onChange={(e) => setShowPast(e.target.checked)} className="rounded accent-indigo-600" />
          Show past
        </label>
      </div>
      {!meetings?.length ? (
        <EmptyState title="No meetings scheduled" hint="Use the calendar button on a forum to schedule one." />
      ) : (
        <div className="space-y-2">
          {meetings.map((meeting) => {
            const allocated = meeting.agenda_items.reduce((sum, item) => sum + item.allocated_minutes, 0)
            return (
              <Link
                key={meeting.id}
                to={`/meetings/${meeting.id}`}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition-colors hover:border-indigo-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-700"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: meeting.forum.colour }} />
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-semibold">{meeting.forum.name}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{fmtDateTime(meeting.scheduled_at)}</div>
                  </div>
                  {meeting.needs_review && <Badge tone="amber">moved — review</Badge>}
                  {meeting.diary_event_id && <Badge tone="blue">linked to diary</Badge>}
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
                  <span>
                    {meeting.agenda_items.length} items · {allocated}/{meeting.forum.capacity_minutes} min
                  </span>
                  <StatusBadge status={meeting.status} />
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <CreateForumModal open={creatingForum} onClose={() => setCreatingForum(false)} people={people} />
      {schedulingFor && <ScheduleModal forum={schedulingFor} onClose={() => setSchedulingFor(null)} />}
    </div>
  )
}

function CreateForumModal({ open, onClose, people }: { open: boolean; onClose: () => void; people: Person[] }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const create = useMutation({
    mutationFn: () =>
      api.post('/forums', {
        name: form.name,
        chair_id: form.chair_id ? Number(form.chair_id) : null,
        cadence: form.cadence || null,
        capacity_minutes: Number(form.capacity_minutes) || 60,
        audience: form.audience || null,
        colour: form.colour || '#0ea5e9',
      }),
    onSuccess: () => {
      toast.success('Forum created')
      setForm({})
      onClose()
      queryClient.invalidateQueries({ queryKey: ['forums'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open={open} onClose={onClose} title="New forum">
      <div className="space-y-3">
        <Field label="Name">
          <Input value={form.name ?? ''} onChange={set('name')} autoFocus placeholder="e.g. AET Weekly" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Chair">
            <Select value={form.chair_id ?? ''} onChange={set('chair_id')}>
              <option value="">None</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Agenda capacity (min)">
            <Input type="number" value={form.capacity_minutes ?? '60'} onChange={set('capacity_minutes')} />
          </Field>
          <Field label="Cadence">
            <Input value={form.cadence ?? ''} onChange={set('cadence')} placeholder="Weekly, Mondays 10:00" />
          </Field>
          <Field label="Colour">
            <Input type="color" value={form.colour ?? '#0ea5e9'} onChange={set('colour')} className="!h-9 !p-1" />
          </Field>
        </div>
        <Field label="Audience">
          <Input value={form.audience ?? ''} onChange={set('audience')} placeholder="Who attends?" />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!form.name} onClick={() => create.mutate()}>
            Create
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ScheduleModal({ forum, onClose }: { forum: Forum; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [when, setWhen] = useState('')
  const create = useMutation({
    mutationFn: () => api.post('/meetings', { forum_id: forum.id, scheduled_at: when }),
    onSuccess: () => {
      toast.success(`${forum.name} scheduled`)
      onClose()
      queryClient.invalidateQueries({ queryKey: ['meetings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Modal open onClose={onClose} title={`Schedule ${forum.name}`}>
      <div className="space-y-3">
        <Field label="Date & time">
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} autoFocus />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!when} onClick={() => create.mutate()}>
            Schedule
          </Button>
        </div>
      </div>
    </Modal>
  )
}
