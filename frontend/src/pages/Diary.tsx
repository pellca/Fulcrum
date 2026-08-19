import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { Upload, UserPlus } from 'lucide-react'
import { api, type DiaryEvent, type Meeting, type Person } from '../api'
import { Badge, Button, Card, Field, Modal, PageHeader, Select } from '../components/ui'

interface ImportSummary {
  added: number
  updated: number
  unchanged: number
  duplicates?: number
  moved_pairs: number
  meetings_updated: number
  unmatched_attendees: string[]
  mailbox?: string
}

export default function Diary() {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [selectedEvent, setSelectedEvent] = useState<DiaryEvent | null>(null)

  const { data: events = [] } = useQuery({
    queryKey: ['diary-events'],
    queryFn: () => api.get<DiaryEvent[]>('/diary/events'),
  })
  const { data: meetings = [] } = useQuery({
    queryKey: ['meetings', 'all'],
    queryFn: () => api.get<Meeting[]>('/meetings'),
  })
  const { data: unmatched = [] } = useQuery({
    queryKey: ['unmatched-attendees'],
    queryFn: () => api.get<string[]>('/diary/unmatched-attendees'),
  })

  const importUpload = useMutation({
    mutationFn: (file: File) => api.upload<ImportSummary>('/diary/import-upload', file),
    onSuccess: (summary) => {
      toast.success(
        `Diary imported: ${summary.added} added, ${summary.updated} updated`,
        {
          description:
            (summary.duplicates ? `${summary.duplicates} duplicate id(s) collapsed. ` : '') +
            (summary.moved_pairs ? `${summary.moved_pairs} meeting(s) detected as moved. ` : '') +
            (summary.meetings_updated ? `${summary.meetings_updated} linked meeting(s) followed the move — review flagged.` : ''),
        },
      )
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  // diary events linked to a Fulcrum meeting take the forum's colour and name
  const meetingByEventId = new Map(
    meetings.filter((m) => m.diary_event_id).map((m) => [m.diary_event_id as string, m]),
  )
  const calendarEvents = [
    ...events.map((event) => {
      const linked = meetingByEventId.get(event.id)
      const linkedTitle =
        linked && event.subject?.toLowerCase() !== linked.forum.name.toLowerCase()
          ? `◆ ${linked.forum.name} · ${event.subject ?? ''}`
          : `◆ ${linked?.forum.name ?? ''}`
      return {
        id: event.id,
        title: linked ? linkedTitle : (event.subject ?? '(no subject)'),
        start: event.start ?? undefined,
        end: event.end ?? undefined,
        allDay: event.is_all_day,
        backgroundColor: linked ? linked.forum.colour : '#64748b',
        borderColor: linked ? linked.forum.colour : '#64748b',
        extendedProps: { kind: 'diary' },
      }
    }),
    // meetings with no diary link still shown as floating markers
    ...meetings
      .filter((meeting) => !meeting.diary_event_id)
      .map((meeting) => ({
        id: `meeting-${meeting.id}`,
        title: `◆ ${meeting.forum.name} (not in diary)`,
        start: meeting.scheduled_at,
        backgroundColor: meeting.forum.colour,
        borderColor: meeting.forum.colour,
        extendedProps: { kind: 'meeting' },
      })),
  ]

  return (
    <div>
      <PageHeader
        title="Diary"
        subtitle={`${events.length} imported diary events · Fulcrum meetings overlaid in colour`}
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) importUpload.mutate(file)
                e.target.value = ''
              }}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={importUpload.isPending}>
              <Upload size={15} /> {importUpload.isPending ? 'Importing…' : 'Import diary.json'}
            </Button>
          </>
        }
      />

      {unmatched.length > 0 && <UnmatchedPanel names={unmatched} />}

      <Card>
        <FullCalendar
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={{ left: 'prev,next today', center: 'title', right: 'timeGridWeek,dayGridMonth' }}
          height="auto"
          weekends={false}
          firstDay={1}
          slotMinTime="07:00:00"
          slotMaxTime="19:00:00"
          nowIndicator
          events={calendarEvents}
          eventClick={(info) => {
            if (info.event.extendedProps.kind === 'diary') {
              const event = events.find((e) => e.id === info.event.id)
              if (event) setSelectedEvent(event)
            } else {
              window.location.href = `/meetings/${info.event.id.replace('meeting-', '')}`
            }
          }}
        />
      </Card>

      {selectedEvent && (
        <EventModal event={selectedEvent} meetings={meetings} onClose={() => setSelectedEvent(null)} />
      )}
    </div>
  )
}

function UnmatchedPanel({ names }: { names: string[] }) {
  const queryClient = useQueryClient()
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const [selection, setSelection] = useState<Record<string, string>>({})

  const map = useMutation({
    mutationFn: ({ alias, personId }: { alias: string; personId: number | null }) =>
      api.post('/diary/map-attendee', { alias, person_id: personId }),
    onSuccess: (_, vars) => {
      toast.success(`Mapped "${vars.alias}"`)
      queryClient.invalidateQueries({ queryKey: ['unmatched-attendees'] })
      queryClient.invalidateQueries({ queryKey: ['people'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          <UserPlus size={14} /> Unrecognised attendees ({names.length})
        </span>
      }
      className="mb-4"
    >
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Diary events only carry display names. Map each name to a person (or create one) so attendance joins up across Fulcrum.
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {names.slice(0, 12).map((name) => (
          <div key={name} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
            <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{name}</span>
            <Select
              value={selection[name] ?? ''}
              onChange={(e) => setSelection((s) => ({ ...s, [name]: e.target.value }))}
              className="!w-40 !py-1 text-xs"
            >
              <option value="">Map to…</option>
              <option value="new">+ New person</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              variant="secondary"
              disabled={!selection[name]}
              onClick={() =>
                map.mutate({ alias: name, personId: selection[name] === 'new' ? null : Number(selection[name]) })
              }
            >
              Map
            </Button>
          </div>
        ))}
      </div>
      {names.length > 12 && <p className="mt-2 text-xs text-slate-400">…and {names.length - 12} more.</p>}
    </Card>
  )
}

function EventModal({ event, meetings, onClose }: { event: DiaryEvent; meetings: Meeting[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [meetingId, setMeetingId] = useState('')
  const linkedMeeting = meetings.find((m) => m.diary_event_id === event.id)

  const link = useMutation({
    mutationFn: (mid: number | null) =>
      api.post('/diary/link-meeting', {
        meeting_id: mid ?? linkedMeeting?.id,
        diary_event_id: mid ? event.id : null,
      }),
    onSuccess: () => {
      toast.success('Link updated')
      queryClient.invalidateQueries({ queryKey: ['meetings'] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open onClose={onClose} title={event.subject ?? '(no subject)'}>
      <div className="space-y-3 text-[13px]">
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="slate">
            {event.start_date} {event.start_time}–{event.end_time}
          </Badge>
          {event.is_recurring && <Badge tone="blue">recurring</Badge>}
          {event.status === 'cancelled' && <Badge tone="red">cancelled</Badge>}
          {event.moved_to_event_id && <Badge tone="amber">moved</Badge>}
        </div>
        {event.location && <p className="text-slate-600 dark:text-slate-300">📍 {event.location}</p>}
        {event.organizer && (
          <p className="text-slate-600 dark:text-slate-300">Organiser: {event.organizer}</p>
        )}
        {event.required_attendees.length > 0 && (
          <p className="text-xs text-slate-500">Required: {event.required_attendees.join(', ')}</p>
        )}
        {event.optional_attendees.length > 0 && (
          <p className="text-xs text-slate-500">Optional: {event.optional_attendees.join(', ')}</p>
        )}
        {event.categories.length > 0 && (
          <div className="flex gap-1">
            {event.categories.map((c) => (
              <Badge key={c} tone="violet">
                {c}
              </Badge>
            ))}
          </div>
        )}

        <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
          {linkedMeeting ? (
            <div className="flex items-center justify-between">
              <span className="text-xs">
                Linked to <strong>{linkedMeeting.forum.name}</strong>
              </span>
              <Button size="sm" variant="secondary" onClick={() => link.mutate(null)}>
                Unlink
              </Button>
            </div>
          ) : (
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Field label="Link to a Fulcrum meeting">
                  <Select value={meetingId} onChange={(e) => setMeetingId(e.target.value)}>
                    <option value="">Choose meeting…</option>
                    {meetings
                      .filter((m) => !m.diary_event_id)
                      .map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.forum.name} — {new Date(m.scheduled_at).toLocaleDateString('en-GB')}
                        </option>
                      ))}
                  </Select>
                </Field>
              </div>
              <Button size="sm" disabled={!meetingId} onClick={() => link.mutate(Number(meetingId))}>
                Link
              </Button>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
