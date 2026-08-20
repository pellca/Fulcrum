import { useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { Link2, Trash2, Upload, UserPlus } from 'lucide-react'
import { api, type DiaryEvent, type Forum, type Meeting, type Person } from '../api'
import { Badge, Button, Card, Field, fmtDateTime, Input, Modal, PageHeader, Select } from '../components/ui'

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

interface LinkSuggestion {
  meeting_id: number
  forum_name: string
  forum_colour: string
  scheduled_at: string
  diary_event_id: string
  subject: string | null
  event_start_date: string | null
  event_start_time: string | null
  location: string | null
  minutes_apart: number
  score: number
  confidence: 'high' | 'likely'
  reasons: string[]
}

interface PurgePreview {
  events: number
  linked_meetings: number
  examples: string[]
  meeting_examples: string[]
}

interface PurgeResult {
  deleted: number
  meetings_unlinked: number
}

function suggestionKey(s: { meeting_id: number; diary_event_id: string }) {
  return `${s.meeting_id}|${s.diary_event_id}`
}

// the diary event's own start_date/start_time (wall-clock, always correct)
// take priority over event.start/event.end (offset-bearing ISO, sometimes
// wrong for already-imported data — see WP-3 note). All-day events have no
// start_time/end_time, so they prefer the wall-clock start_date/end_date
// over the offset-bearing start/end for the same reason.
function eventStart(event: DiaryEvent): string | undefined {
  if (event.is_all_day) return event.start_date ?? event.start ?? undefined
  if (event.start_date && event.start_time) return `${event.start_date}T${event.start_time}`
  return event.start ?? undefined
}
function eventEnd(event: DiaryEvent): string | undefined {
  if (event.is_all_day) return event.end_date ?? event.end ?? undefined
  if (event.end_date && event.end_time) return `${event.end_date}T${event.end_time}`
  return event.end ?? undefined
}

export default function Diary() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [showUnlinked, setShowUnlinked] = useState(false)
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<string>>(new Set())
  const [purging, setPurging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const raw = searchParams.get('event')
    if (raw) {
      setSelectedEventId(raw)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

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
  const { data: suggestions = [] } = useQuery({
    queryKey: ['diary-link-suggestions'],
    queryFn: () => api.get<LinkSuggestion[]>('/diary/link-suggestions?limit=25&within_minutes=120'),
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
  // meetings that currently have a link suggestion would otherwise duplicate
  // their own diary event as a floating marker — suppress those
  const suggestionMeetingIds = new Set(suggestions.map((s) => s.meeting_id))

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
        start: eventStart(event),
        end: eventEnd(event),
        allDay: event.is_all_day,
        backgroundColor: linked ? linked.forum.colour : '#64748b',
        borderColor: linked ? linked.forum.colour : '#64748b',
        extendedProps: { kind: 'diary' },
      }
    }),
    // meetings with no diary link — hidden by default (this was the source
    // of duplicate-looking markers sitting beside their real diary event);
    // shown only as a diagnostic when the toggle is on, dashed to read as such
    ...(showUnlinked
      ? meetings
          .filter((meeting) => !meeting.diary_event_id && !suggestionMeetingIds.has(meeting.id))
          .map((meeting) => ({
            id: `meeting-${meeting.id}`,
            title: `◆ ${meeting.forum.name} (not in diary)`,
            start: meeting.scheduled_at,
            backgroundColor: meeting.forum.colour,
            borderColor: meeting.forum.colour,
            classNames: ['diary-unlinked-marker'],
            extendedProps: { kind: 'meeting' },
          }))
      : []),
  ]

  const visibleSuggestions = suggestions.filter((s) => !dismissedSuggestions.has(suggestionKey(s)))

  return (
    <div>
      <style>{'.diary-unlinked-marker{border-style:dashed!important;border-width:2px!important;}'}</style>
      <PageHeader
        title="Diary"
        subtitle={`${events.length} imported diary events · Fulcrum meetings overlaid in colour`}
        actions={
          <>
            <Button variant="secondary" onClick={() => setPurging(true)}>
              <Trash2 size={15} /> Purge range…
            </Button>
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

      {visibleSuggestions.length > 0 && (
        <LinkSuggestionsPanel
          suggestions={visibleSuggestions}
          onDismiss={(key) => setDismissedSuggestions((prev) => new Set(prev).add(key))}
        />
      )}

      <label className="mb-3 flex cursor-pointer items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
        <input
          type="checkbox"
          checked={showUnlinked}
          onChange={(e) => setShowUnlinked(e.target.checked)}
          className="rounded accent-indigo-600"
        />
        Show unlinked meetings
      </label>

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
              setSelectedEventId(info.event.id)
            } else {
              navigate(`/meetings/${info.event.id.replace('meeting-', '')}`)
            }
          }}
        />
      </Card>

      {selectedEventId &&
        (() => {
          const event = events.find((e) => e.id === selectedEventId)
          return event ? (
            <EventModal event={event} meetings={meetings} onClose={() => setSelectedEventId(null)} />
          ) : null
        })()}

      <PurgeModal open={purging} onClose={() => setPurging(false)} />
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

function LinkSuggestionsPanel({
  suggestions,
  onDismiss,
}: {
  suggestions: LinkSuggestion[]
  onDismiss: (key: string) => void
}) {
  const queryClient = useQueryClient()

  const link = useMutation({
    mutationFn: (s: LinkSuggestion) =>
      api.post('/diary/link-meeting', { meeting_id: s.meeting_id, diary_event_id: s.diary_event_id }),
    onSuccess: (_, s) => {
      toast.success(`Linked ${s.forum_name}`)
      queryClient.invalidateQueries({ queryKey: ['meetings'] })
      queryClient.invalidateQueries({ queryKey: ['diary-link-suggestions'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          <Link2 size={14} /> Possible diary links ({suggestions.length})
        </span>
      }
      className="mb-4"
    >
      <div className="space-y-2">
        {suggestions.slice(0, 6).map((s) => {
          const key = suggestionKey(s)
          return (
            <div
              key={key}
              title={s.reasons.join('\n')}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-[13px] dark:bg-slate-800/60"
            >
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.forum_colour }} />
              <span className="min-w-0 flex-1 truncate">
                <strong>{s.forum_name}</strong> — {fmtDateTime(s.scheduled_at)}
              </span>
              <span className="text-slate-400">↔</span>
              <span className="min-w-0 flex-1 truncate text-slate-600 dark:text-slate-300">
                {s.subject ?? '(no subject)'} — {s.event_start_date} {s.event_start_time}
              </span>
              <Badge tone={s.confidence === 'high' ? 'green' : 'amber'}>{s.confidence}</Badge>
              <Button size="sm" disabled={link.isPending} onClick={() => link.mutate(s)}>
                Link
              </Button>
              <Button size="sm" variant="secondary" onClick={() => onDismiss(key)}>
                Not a match
              </Button>
            </div>
          )
        })}
      </div>
      {suggestions.length > 6 && <p className="mt-2 text-xs text-slate-400">…and {suggestions.length - 6} more.</p>}
    </Card>
  )
}

function EventModal({ event, meetings, onClose }: { event: DiaryEvent; meetings: Meeting[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [meetingId, setMeetingId] = useState('')
  const linkedMeeting = meetings.find((m) => m.diary_event_id === event.id)

  const [forumMode, setForumMode] = useState<'existing' | 'new'>('existing')
  const [createForumId, setCreateForumId] = useState('')
  const [newForumName, setNewForumName] = useState(event.subject ?? '')
  const [newForumColour, setNewForumColour] = useState('#0ea5e9')
  const [newForumCapacity, setNewForumCapacity] = useState('60')

  const { data: forums = [] } = useQuery({ queryKey: ['forums'], queryFn: () => api.get<Forum[]>('/forums') })

  const link = useMutation({
    mutationFn: (mid: number | null) =>
      api.post('/diary/link-meeting', {
        meeting_id: mid ?? linkedMeeting?.id,
        diary_event_id: mid ? event.id : null,
      }),
    onSuccess: () => {
      toast.success('Link updated')
      queryClient.invalidateQueries({ queryKey: ['meetings'] })
      queryClient.invalidateQueries({ queryKey: ['diary-link-suggestions'] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const createMeeting = useMutation({
    mutationFn: () =>
      api.post<Meeting>('/diary/create-meeting', {
        diary_event_id: event.id,
        ...(forumMode === 'existing'
          ? { forum_id: Number(createForumId) }
          : {
              new_forum_name: newForumName.trim(),
              new_forum_colour: newForumColour,
              new_forum_capacity_minutes: newForumCapacity ? Number(newForumCapacity) : undefined,
            }),
      }),
    onSuccess: () => {
      toast.success('Meeting created and linked')
      queryClient.invalidateQueries()
      onClose()
    },
    onError: (e: Error) =>
      toast.error(e.message === 'Conflict' ? 'This event already has a meeting' : e.message),
  })

  const createDisabled =
    createMeeting.isPending ||
    (forumMode === 'existing' ? !createForumId : !newForumName.trim())

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
              <div className="flex items-center gap-3">
                <Link
                  to={`/meetings/${linkedMeeting.id}`}
                  className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  Open meeting →
                </Link>
                <Button size="sm" variant="secondary" onClick={() => link.mutate(null)}>
                  Unlink
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
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

              <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
                <p className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                  Create a meeting from this event
                </p>
                <div className="mb-2 flex gap-1">
                  <Button
                    size="sm"
                    variant={forumMode === 'existing' ? 'primary' : 'secondary'}
                    onClick={() => setForumMode('existing')}
                  >
                    Existing forum
                  </Button>
                  <Button
                    size="sm"
                    variant={forumMode === 'new' ? 'primary' : 'secondary'}
                    onClick={() => setForumMode('new')}
                  >
                    New forum
                  </Button>
                </div>
                {forumMode === 'existing' ? (
                  <Field label="Forum">
                    <Select value={createForumId} onChange={(e) => setCreateForumId(e.target.value)}>
                      <option value="">Choose forum…</option>
                      {forums.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : (
                  <div className="grid grid-cols-[1fr_auto_auto] gap-2">
                    <Field label="Forum name">
                      <Input value={newForumName} onChange={(e) => setNewForumName(e.target.value)} />
                    </Field>
                    <Field label="Colour">
                      <Input
                        type="color"
                        value={newForumColour}
                        onChange={(e) => setNewForumColour(e.target.value)}
                        className="!w-14 !px-1 !py-1"
                      />
                    </Field>
                    <Field label="Capacity (min)">
                      <Input
                        type="number"
                        min={15}
                        max={480}
                        value={newForumCapacity}
                        onChange={(e) => setNewForumCapacity(e.target.value)}
                        className="!w-20"
                      />
                    </Field>
                  </div>
                )}
                <div className="mt-2 flex justify-end">
                  <Button size="sm" disabled={createDisabled} onClick={() => createMeeting.mutate()}>
                    Create meeting
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

// Local date parts, not UTC — toISOString() would read "yesterday" for the
// first hour after local midnight whenever the local offset is ahead of UTC
// (e.g. 00:00–01:00 BST).
function isoDate(d: Date) {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function PurgeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [fromDate, setFromDate] = useState(() => isoDate(new Date(Date.now() - 90 * 86400000)))
  const [toDate, setToDate] = useState(() => isoDate(new Date()))
  const [includeCancelled, setIncludeCancelled] = useState(true)
  const [confirmText, setConfirmText] = useState('')
  const [preview, setPreview] = useState<PurgePreview | null>(null)

  const invalidatePreview = () => setPreview(null)

  const runPreview = useMutation({
    mutationFn: () =>
      api.post<PurgePreview>('/diary/purge-preview', {
        from_date: fromDate,
        to_date: toDate,
        include_cancelled: includeCancelled,
      }),
    onSuccess: (data) => setPreview(data),
    onError: (e: Error) => toast.error(e.message),
  })

  const runPurge = useMutation({
    mutationFn: () =>
      api.post<PurgeResult>('/diary/purge', {
        from_date: fromDate,
        to_date: toDate,
        include_cancelled: includeCancelled,
        confirm: confirmText,
      }),
    onSuccess: (result) => {
      toast.success(
        `Purged ${result.deleted} event(s)`,
        {
          description: result.meetings_unlinked
            ? `${result.meetings_unlinked} meeting(s) unlinked.`
            : undefined,
        },
      )
      queryClient.invalidateQueries()
      close()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const close = () => {
    setPreview(null)
    setConfirmText('')
    onClose()
  }

  const rangeInvalid = !fromDate || !toDate || fromDate > toDate

  return (
    <Modal open={open} onClose={close} title="Purge diary range">
      <div className="space-y-3 text-[13px]">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Permanently deletes imported diary events in a date range. Fulcrum meetings themselves are never deleted —
          any that are linked to a purged event simply lose that link.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="From">
            <Input
              type="date"
              value={fromDate}
              onChange={(e) => {
                setFromDate(e.target.value)
                invalidatePreview()
              }}
            />
          </Field>
          <Field label="To">
            <Input
              type="date"
              value={toDate}
              onChange={(e) => {
                setToDate(e.target.value)
                invalidatePreview()
              }}
            />
          </Field>
        </div>
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={includeCancelled}
            onChange={(e) => {
              setIncludeCancelled(e.target.checked)
              invalidatePreview()
            }}
            className="rounded accent-indigo-600"
          />
          Include cancelled events
        </label>

        <div className="flex justify-end">
          <Button
            size="sm"
            variant="secondary"
            disabled={rangeInvalid || runPreview.isPending}
            onClick={() => runPreview.mutate()}
          >
            {runPreview.isPending ? 'Previewing…' : 'Preview'}
          </Button>
        </div>

        {preview && (
          <div className="rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
            <p className="font-medium text-slate-700 dark:text-slate-200">
              {preview.events} event(s) in range
              {preview.linked_meetings > 0 && `, ${preview.linked_meetings} linked to a meeting`}
            </p>
            {preview.examples.length > 0 && (
              <p className="mt-1 text-slate-500 dark:text-slate-400">Examples: {preview.examples.join(', ')}</p>
            )}
            {preview.meeting_examples.length > 0 && (
              <p className="mt-1 text-slate-500 dark:text-slate-400">
                Affected meetings: {preview.meeting_examples.join(', ')}
              </p>
            )}
            {preview.linked_meetings > 0 && (
              <p className="mt-2 font-medium text-rose-600 dark:text-rose-400">
                {preview.linked_meetings} Fulcrum meeting(s) will lose their diary link — the meetings themselves are
                kept.
              </p>
            )}
          </div>
        )}

        <Field label={'Type DELETE to confirm'}>
          <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="DELETE" />
        </Field>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={!preview || confirmText !== 'DELETE' || runPurge.isPending}
            onClick={() => runPurge.mutate()}
          >
            {runPurge.isPending ? 'Deleting…' : 'Delete'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
