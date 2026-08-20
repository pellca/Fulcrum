import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ArrowLeft, GripVertical, Pencil, Plus, Printer, Trash2 } from 'lucide-react'
import { api, type Decision, type Meeting, type Person, type ScoredTopic } from '../api'
import { MeetingEditModal } from '../components/meetingForms'
import {
  allocatedMinutes,
  Badge,
  Button,
  CapacityBar,
  Card,
  EmptyState,
  Field,
  fmtDate,
  fmtDateTime,
  Input,
  IntentBadge,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
  cn,
} from '../components/ui'

export default function MeetingDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const meetingKey = ['meeting', id]
  const [editing, setEditing] = useState(false)

  const { data: meeting } = useQuery({
    queryKey: meetingKey,
    queryFn: () => api.get<Meeting>(`/meetings/${id}`),
  })
  const { data: candidates = [] } = useQuery({
    queryKey: ['candidates', id],
    queryFn: () => api.get<ScoredTopic[]>(`/meetings/${id}/candidates`),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: meetingKey })
    queryClient.invalidateQueries({ queryKey: ['candidates', id] })
    queryClient.invalidateQueries({ queryKey: ['meetings'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['rolling-agenda'] })
  }

  const patchMeeting = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/meetings/${id}`, body),
    onSuccess: invalidate,
  })
  const addItem = useMutation({
    mutationFn: (topicId: number) => api.post(`/meetings/${id}/agenda`, { topic_id: topicId }),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  })
  const removeItem = useMutation({
    mutationFn: (itemId: number) => api.delete(`/agenda-items/${itemId}`),
    onSuccess: invalidate,
  })
  const patchItem = useMutation({
    mutationFn: ({ itemId, body }: { itemId: number; body: Record<string, unknown> }) =>
      api.patch(`/agenda-items/${itemId}`, body),
    onSuccess: invalidate,
  })
  const reorder = useMutation({
    mutationFn: (itemIds: number[]) => api.post(`/meetings/${id}/agenda/reorder`, { item_ids: itemIds }),
    onSuccess: invalidate,
  })

  if (!meeting) return <Spinner />

  const allocated = allocatedMinutes(meeting.agenda_items)
  const capacity = meeting.forum.capacity_minutes
  const over = allocated > capacity

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over: dropTarget } = event
    if (!dropTarget || active.id === dropTarget.id) return
    const ids = meeting.agenda_items.map((item) => item.id)
    const moved = arrayMove(ids, ids.indexOf(Number(active.id)), ids.indexOf(Number(dropTarget.id)))
    reorder.mutate(moved)
  }

  return (
    <div>
      <div className="no-print">
        <Link to="/meetings" className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-indigo-600">
          <ArrowLeft size={13} /> All meetings
        </Link>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              <span className="h-3 w-3 rounded-full" style={{ background: meeting.forum.colour }} />
              {meeting.forum.name}
              {meeting.needs_review && <Badge tone="amber">diary moved — check time</Badge>}
            </h1>
            <p className="mt-0.5 flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              {fmtDateTime(meeting.scheduled_at)}
              {meeting.diary_event_id && (
                <Link
                  to={`/diary?event=${encodeURIComponent(meeting.diary_event_id)}`}
                  className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  In diary →
                </Link>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {meeting.needs_review && (
              <Button size="sm" variant="secondary" onClick={() => patchMeeting.mutate({ needs_review: false })}>
                Time confirmed
              </Button>
            )}
            <Select
              value={meeting.status}
              onChange={(e) => patchMeeting.mutate({ status: e.target.value })}
              className="!w-36"
            >
              {['planned', 'agenda_set', 'held', 'cancelled'].map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </Select>
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil size={15} /> Edit
            </Button>
            <Button variant="secondary" onClick={() => window.print()}>
              <Printer size={15} /> Print agenda
            </Button>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-5">
          <div className="space-y-4 xl:col-span-3">
            <Card
              title="Agenda"
              actions={
                <span className={cn('text-xs font-semibold', over ? 'text-rose-500' : 'text-slate-500')}>
                  {allocated} / {capacity} min
                </span>
              }
            >
              <CapacityBar allocated={allocated} capacity={capacity} className="mb-3" />
              {meeting.agenda_items.length === 0 ? (
                <EmptyState title="Empty agenda" hint="Add topics from the ranked candidates — Fulcrum has already scored what most deserves the time." />
              ) : (
                <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                  <SortableContext items={meeting.agenda_items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
                    <div className="space-y-2">
                      {meeting.agenda_items.map((item, index) => (
                        <SortableAgendaRow
                          key={item.id}
                          item={item}
                          index={index}
                          held={meeting.status === 'held'}
                          onMinutes={(minutes) => patchItem.mutate({ itemId: item.id, body: { allocated_minutes: minutes } })}
                          onOutcome={(note) => patchItem.mutate({ itemId: item.id, body: { outcome_note: note } })}
                          onRemove={() => removeItem.mutate(item.id)}
                        />
                      ))}
                    </div>
                  </SortableContext>
                </DndContext>
              )}
            </Card>

            {meeting.status === 'held' && <CaptureCard meetingId={meeting.id} />}
          </div>

          <div className="xl:col-span-2">
            <Card title="Candidate topics — ranked">
              {candidates.length === 0 ? (
                <EmptyState title="No candidates" hint="Create topics on the Topics page; anything proposed or parked appears here, scored." />
              ) : (
                <div className="space-y-2">
                  {candidates.map(({ topic, score, reasons }) => (
                    <div key={topic.id} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[13px] leading-snug font-medium">{topic.title}</div>
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <IntentBadge intent={topic.intent} />
                            <Badge tone="slate">{topic.duration_minutes}m</Badge>
                            {topic.recurring && <Badge tone="amber">standing</Badge>}
                            {topic.sponsor && <Badge tone="slate">{topic.sponsor.name}</Badge>}
                            {topic.target_by && <Badge tone="amber">by {fmtDate(topic.target_by)}</Badge>}
                          </div>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <span
                            className={cn(
                              'rounded-md px-1.5 py-0.5 text-xs font-bold',
                              score >= 50
                                ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
                            )}
                            title={reasons.join('\n')}
                          >
                            {Math.round(score)}
                          </span>
                          <Button size="sm" variant="ghost" onClick={() => addItem.mutate(topic.id)}>
                            <Plus size={13} /> Add
                          </Button>
                        </div>
                      </div>
                      {reasons.length > 0 && (
                        <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                          {reasons.slice(0, 3).map((reason) => (
                            <li key={reason}>• {reason}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>

      {/* print-only clean agenda */}
      <div className="hidden print:block">
        <h1 className="text-2xl font-bold">{meeting.forum.name}</h1>
        <p className="mb-1 text-sm">{fmtDateTime(meeting.scheduled_at)}</p>
        {meeting.forum.audience && <p className="mb-4 text-sm text-slate-600">Attendees: {meeting.forum.audience}</p>}
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b-2 border-slate-800 text-left">
              <th className="py-1.5 pr-3">#</th>
              <th className="py-1.5 pr-3">Item</th>
              <th className="py-1.5 pr-3">Intent</th>
              <th className="py-1.5 pr-3">Sponsor</th>
              <th className="py-1.5">Time</th>
            </tr>
          </thead>
          <tbody>
            {meeting.agenda_items.map((item, index) => (
              <tr key={item.id} className="border-b border-slate-300 align-top">
                <td className="py-2 pr-3">{index + 1}</td>
                <td className="py-2 pr-3 font-medium">{item.topic.title}</td>
                <td className="py-2 pr-3 capitalize">{item.topic.intent}</td>
                <td className="py-2 pr-3">{item.topic.sponsor?.name ?? '—'}</td>
                <td className="py-2">{item.allocated_minutes} min</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-500">
          Total {allocated} of {capacity} minutes · prepared with Fulcrum
        </p>
      </div>

      {editing && (
        <MeetingEditModal
          meeting={meeting}
          onClose={() => setEditing(false)}
          onDeleted={() => navigate('/meetings')}
        />
      )}
    </div>
  )
}

function SortableAgendaRow({
  item,
  index,
  held,
  onMinutes,
  onOutcome,
  onRemove,
}: {
  item: Meeting['agenda_items'][number]
  index: number
  held: boolean
  onMinutes: (m: number) => void
  onOutcome: (note: string) => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900',
        isDragging && 'z-10 opacity-80 shadow-lg',
      )}
    >
      <div className="flex items-center gap-2">
        <button {...attributes} {...listeners} className="cursor-grab text-slate-300 hover:text-slate-500 active:cursor-grabbing">
          <GripVertical size={15} />
        </button>
        <span className="w-5 text-xs font-bold text-slate-400">{index + 1}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium">{item.topic.title}</div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <IntentBadge intent={item.topic.intent} />
            {item.topic.recurring && <Badge tone="amber">standing</Badge>}
            {item.topic.sponsor && <span>{item.topic.sponsor.name}</span>}
          </div>
        </div>
        <Input
          type="number"
          defaultValue={item.allocated_minutes}
          onBlur={(e) => {
            const minutes = Number(e.target.value)
            if (minutes && minutes !== item.allocated_minutes) onMinutes(minutes)
          }}
          className="!w-16 !px-2 !py-1 text-center text-xs"
          title="Allocated minutes"
        />
        <button onClick={onRemove} className="text-slate-300 hover:text-rose-500">
          <Trash2 size={14} />
        </button>
      </div>
      {held && (
        <div className="mt-2 pl-9">
          <Textarea
            rows={1}
            placeholder="Outcome / what was agreed…"
            defaultValue={item.outcome_note ?? ''}
            onBlur={(e) => e.target.value !== (item.outcome_note ?? '') && onOutcome(e.target.value)}
            className="!text-xs"
          />
        </div>
      )}
    </div>
  )
}

function CaptureCard({ meetingId }: { meetingId: number }) {
  const queryClient = useQueryClient()
  const { data: decisions = [] } = useQuery({
    queryKey: ['decisions', meetingId],
    queryFn: () => api.get<Decision[]>(`/decisions?meeting_id=${meetingId}`),
  })
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const [title, setTitle] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [reviewOn, setReviewOn] = useState('')
  const [spawnAction, setSpawnAction] = useState(true)
  const [actionTitle, setActionTitle] = useState('')
  const [actionDue, setActionDue] = useState('')

  const add = useMutation({
    mutationFn: async () => {
      const decision = await api.post<Decision>('/decisions', {
        meeting_id: meetingId,
        title,
        decided_on: new Date().toISOString().slice(0, 10),
        owner_id: ownerId ? Number(ownerId) : null,
        review_on: reviewOn || null,
      })
      if (spawnAction && actionTitle) {
        const action = await api.post<{ id: number }>('/actions', {
          title: actionTitle,
          owner_id: ownerId ? Number(ownerId) : null,
          due_date: actionDue || null,
        })
        await api.post('/links', {
          from_type: 'decision',
          from_id: decision.id,
          to_type: 'action',
          to_id: action.id,
          kind: 'informs',
          rationale: 'Action arising from decision',
        })
      }
      return decision
    },
    onSuccess: () => {
      toast.success('Decision captured')
      setTitle('')
      setReviewOn('')
      setActionTitle('')
      setActionDue('')
      queryClient.invalidateQueries({ queryKey: ['decisions', meetingId] })
      queryClient.invalidateQueries({ queryKey: ['actions'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Card title="Decisions from this meeting">
      {decisions.length > 0 && (
        <ul className="mb-3 space-y-1.5">
          {decisions.map((decision) => (
            <li key={decision.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
              <span className="min-w-0 truncate font-medium">{decision.title}</span>
              <span className="flex shrink-0 items-center gap-1.5">
                {decision.owner && <span className="text-slate-500">{decision.owner.name}</span>}
                <StatusBadge status={decision.status} />
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="space-y-2 rounded-lg border border-slate-100 p-3 dark:border-slate-800">
        <Field label="Decision">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What was decided?" />
        </Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label="Owner">
            <Select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
              <option value="">None</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Revisit on (optional)">
            <Input type="date" value={reviewOn} onChange={(e) => setReviewOn(e.target.value)} title="The decision resurfaces on the dashboard on this date" />
          </Field>
          <label className="flex items-end gap-1.5 pb-2 text-[13px] text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={spawnAction} onChange={(e) => setSpawnAction(e.target.checked)} className="rounded accent-indigo-600" />
            Spawn follow-up action
          </label>
        </div>
        {spawnAction && (
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <Field label="Action title">
                <Input value={actionTitle} onChange={(e) => setActionTitle(e.target.value)} placeholder="What must happen next?" />
              </Field>
            </div>
            <Field label="Due">
              <Input type="date" value={actionDue} onChange={(e) => setActionDue(e.target.value)} />
            </Field>
          </div>
        )}
        <Button size="sm" disabled={!title} onClick={() => add.mutate()}>
          Capture decision
        </Button>
      </div>
    </Card>
  )
}
