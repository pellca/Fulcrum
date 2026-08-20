import { useState } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, Trash2 } from 'lucide-react'
import { api, type Forum, type Meeting, type Person } from '../api'
import { Button, Field, Input, Modal, Select, Textarea } from './ui'

interface BulkCheckResult {
  type: string
  label: string
  requested: number
  found: number
  titles: string[]
  warnings: { label: string; count: number; examples: string[] }[]
}

const MEETING_STATUSES = ['planned', 'agenda_set', 'held', 'cancelled']

function toLocalInput(iso: string) {
  return iso.slice(0, 16)
}

function invalidateMeetingQueries(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['meetings'] })
  queryClient.invalidateQueries({ queryKey: ['forums'] })
  queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  queryClient.invalidateQueries({ queryKey: ['rolling-agenda'] })
}

/** Shared preflight-confirm modal for bulk/check-backed deletes. */
function PreflightModal({
  check,
  onCancel,
  onConfirm,
  pending,
  confirmLabel,
}: {
  check: BulkCheckResult
  onCancel: () => void
  onConfirm: () => void
  pending: boolean
  confirmLabel: string
}) {
  return (
    <Modal open onClose={onCancel} title={`Delete ${check.found} ${check.label}?`}>
      <div className="space-y-3">
        <ul className="max-h-40 space-y-0.5 overflow-y-auto rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
          {check.titles.map((title, i) => (
            <li key={i} className="truncate">
              {title}
            </li>
          ))}
          {check.found > check.titles.length && (
            <li className="text-slate-400">…and {check.found - check.titles.length} more</li>
          )}
        </ul>

        {check.warnings.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
            <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-amber-800 dark:text-amber-300">
              <AlertTriangle size={13} /> This will also affect:
            </p>
            <ul className="space-y-1 text-xs">
              {check.warnings.map((warning) => (
                <li key={warning.label}>
                  <span className="font-medium">
                    {warning.count} {warning.label}
                  </span>
                  {warning.examples.length > 0 && (
                    <span className="text-slate-500 dark:text-slate-400">
                      {' '}
                      — {warning.examples.slice(0, 3).join(', ')}
                      {warning.count > 3 ? '…' : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={pending}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function MeetingEditModal({
  meeting,
  onClose,
  onDeleted,
}: {
  meeting: Meeting
  onClose: () => void
  onDeleted?: () => void
}) {
  const queryClient = useQueryClient()
  const initialScheduledAt = toLocalInput(meeting.scheduled_at)
  const [scheduledAt, setScheduledAt] = useState(initialScheduledAt)
  const [status, setStatus] = useState(meeting.status)
  const [notes, setNotes] = useState(meeting.notes ?? '')
  const [check, setCheck] = useState<BulkCheckResult | null>(null)

  const dirty = scheduledAt !== initialScheduledAt || status !== meeting.status || notes !== (meeting.notes ?? '')

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {}
      if (scheduledAt !== initialScheduledAt) body.scheduled_at = scheduledAt
      if (status !== meeting.status) body.status = status
      if (notes !== (meeting.notes ?? '')) body.notes = notes
      return api.patch(`/meetings/${meeting.id}`, body)
    },
    onSuccess: () => {
      toast.success('Meeting updated')
      invalidateMeetingQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['meeting', String(meeting.id)] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const preflight = useMutation({
    mutationFn: () => api.post<BulkCheckResult>('/bulk/check', { type: 'meeting', ids: [meeting.id] }),
    onSuccess: setCheck,
    onError: (e: Error) => toast.error(e.message),
  })

  const del = useMutation({
    mutationFn: () => api.delete(`/meetings/${meeting.id}`),
    onSuccess: () => {
      toast.success('Meeting deleted')
      invalidateMeetingQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['meeting', String(meeting.id)] })
      setCheck(null)
      onClose()
      onDeleted?.()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <>
      <Modal open onClose={onClose} title={`Edit — ${meeting.forum.name}`}>
        <div className="space-y-3">
          <Field label="Date & time">
            <Input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} autoFocus />
          </Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {MEETING_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Notes">
            <Textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything worth remembering about this meeting…"
            />
          </Field>

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              Save
            </Button>
          </div>

          <div className="mt-2 flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2.5 dark:border-rose-900 dark:bg-rose-950/30">
            <span className="text-xs text-rose-700 dark:text-rose-300">
              Deleting removes this meeting's agenda and unlinks any decisions captured against it.
            </span>
            <Button size="sm" variant="danger" onClick={() => preflight.mutate()} disabled={preflight.isPending}>
              <Trash2 size={13} /> Delete
            </Button>
          </div>
        </div>
      </Modal>

      {check && (
        <PreflightModal
          check={check}
          onCancel={() => setCheck(null)}
          onConfirm={() => del.mutate()}
          pending={del.isPending}
          confirmLabel="Delete meeting"
        />
      )}
    </>
  )
}

export function ForumFormModal({ forum, onClose }: { forum: Forum | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const [form, setForm] = useState<Record<string, string>>(() =>
    forum
      ? {
          name: forum.name,
          chair_id: forum.chair ? String(forum.chair.id) : '',
          cadence: forum.cadence ?? '',
          capacity_minutes: String(forum.capacity_minutes),
          audience: forum.audience ?? '',
          colour: forum.colour,
        }
      : ({} as Record<string, string>),
  )
  const [check, setCheck] = useState<BulkCheckResult | null>(null)
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        chair_id: form.chair_id ? Number(form.chair_id) : null,
        cadence: form.cadence || null,
        capacity_minutes: Number(form.capacity_minutes) || 60,
        audience: form.audience || null,
        colour: form.colour || '#0ea5e9',
      }
      return forum ? api.patch(`/forums/${forum.id}`, body) : api.post('/forums', body)
    },
    onSuccess: () => {
      toast.success(forum ? 'Forum updated' : 'Forum created')
      invalidateMeetingQueries(queryClient)
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const preflight = useMutation({
    mutationFn: () => api.post<BulkCheckResult>('/bulk/check', { type: 'forum', ids: [forum!.id] }),
    onSuccess: setCheck,
    onError: (e: Error) => toast.error(e.message),
  })

  const del = useMutation({
    mutationFn: () => api.delete(`/forums/${forum!.id}`),
    onSuccess: () => {
      toast.success('Forum deleted')
      invalidateMeetingQueries(queryClient)
      setCheck(null)
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <>
      <Modal open onClose={onClose} title={forum ? `Edit — ${forum.name}` : 'New forum'}>
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
            <Button disabled={!form.name || save.isPending} onClick={() => save.mutate()}>
              {forum ? 'Save' : 'Create'}
            </Button>
          </div>

          {forum && (
            <div className="mt-2 flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2.5 dark:border-rose-900 dark:bg-rose-950/30">
              <span className="text-xs text-rose-700 dark:text-rose-300">
                Deleting a forum deletes every meeting scheduled under it — agendas and all.
              </span>
              <Button size="sm" variant="danger" onClick={() => preflight.mutate()} disabled={preflight.isPending}>
                <Trash2 size={13} /> Delete
              </Button>
            </div>
          )}
        </div>
      </Modal>

      {check && forum && (
        <PreflightModal
          check={check}
          onCancel={() => setCheck(null)}
          onConfirm={() => del.mutate()}
          pending={del.isPending}
          confirmLabel="Delete forum"
        />
      )}
    </>
  )
}
