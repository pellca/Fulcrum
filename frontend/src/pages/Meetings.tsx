import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { CalendarPlus, LayoutGrid, Landmark, Pencil, Plus } from 'lucide-react'
import { api, type Forum, type Meeting } from '../api'
import { ForumFormModal, MeetingEditModal } from '../components/meetingForms'
import {
  allocatedMinutes,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  fmtDateTime,
  Input,
  Modal,
  PageHeader,
  Spinner,
  StatusBadge,
} from '../components/ui'

export default function Meetings() {
  const [showPast, setShowPast] = useState(false)
  // undefined = closed, null = create mode, Forum = edit mode
  const [formingForum, setFormingForum] = useState<Forum | null | undefined>(undefined)
  const [schedulingFor, setSchedulingFor] = useState<Forum | null>(null)
  const [editingMeeting, setEditingMeeting] = useState<Meeting | null>(null)

  const { data: forums, isLoading: loadingForums } = useQuery({ queryKey: ['forums'], queryFn: () => api.get<Forum[]>('/forums') })
  const { data: meetings, isLoading: loadingMeetings } = useQuery({
    queryKey: ['meetings', showPast],
    queryFn: () => api.get<Meeting[]>(`/meetings${showPast ? '' : '?upcoming_only=true'}`),
  })

  if (loadingForums || loadingMeetings) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Meetings"
        subtitle="Your governance forums and their agenda pipeline"
        actions={
          <Button variant="secondary" onClick={() => setFormingForum(null)}>
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
              <div className="flex shrink-0 items-center gap-1">
                <Link to={`/forums/${forum.id}/agenda`}>
                  <Button size="sm" variant="ghost" title="Agenda board">
                    <LayoutGrid size={15} />
                  </Button>
                </Link>
                <Button size="sm" variant="ghost" onClick={() => setFormingForum(forum)} title="Edit forum">
                  <Pencil size={15} />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSchedulingFor(forum)} title="Schedule a meeting">
                  <CalendarPlus size={15} />
                </Button>
              </div>
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
            const allocated = allocatedMinutes(meeting.agenda_items)
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
                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      setEditingMeeting(meeting)
                    }}
                    className="rounded-md p-1 text-slate-300 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
                    title="Edit meeting"
                  >
                    <Pencil size={13} />
                  </button>
                </div>
              </Link>
            )
          })}
        </div>
      )}

      {formingForum !== undefined && <ForumFormModal forum={formingForum} onClose={() => setFormingForum(undefined)} />}
      {schedulingFor && <ScheduleModal forum={schedulingFor} onClose={() => setSchedulingFor(null)} />}
      {editingMeeting && (
        <MeetingEditModal
          meeting={editingMeeting}
          onClose={() => setEditingMeeting(null)}
          onDeleted={() => setEditingMeeting(null)}
        />
      )}
    </div>
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
