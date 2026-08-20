import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Download, Plus } from 'lucide-react'
import { api, type Commitment, type Person, type Topic, type Workstream } from '../api'
import { ImportCsvButton } from '../components/CsvImport'
import { BulkBar, SelectCheckbox, useSelection, type Id } from '../components/BulkSelect'
import {
  Badge,
  Button,
  cn,
  dueTone,
  EmptyState,
  Field,
  fmtDate,
  Input,
  IntentBadge,
  Modal,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
} from '../components/ui'
import { Drawer, LinkPanel, Section } from '../components/panels'

const INTENTS = ['decide', 'inform', 'consult', 'shape']
const TOPIC_STATUSES = ['proposed', 'scheduled', 'discussed', 'parked']

export default function Topics() {
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const selection = useSelection()

  useEffect(() => {
    const open = Number(searchParams.get('open'))
    if (open) {
      setSelectedId(open)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const { data: topics, isLoading } = useQuery({
    queryKey: ['topics', status],
    queryFn: () => api.get<Topic[]>(`/topics${status ? `?status=${status}` : ''}`),
  })
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const { data: workstreams = [] } = useQuery({ queryKey: ['workstreams'], queryFn: () => api.get<Workstream[]>('/workstreams') })

  return (
    <div>
      <PageHeader
        title="Topics"
        subtitle="Discussion items competing for meeting time"
        actions={
          <>
            <a href="/api/imports/templates/topics" download>
              <Button variant="ghost" title="Download the CSV template for topics">
                <Download size={15} /> Template
              </Button>
            </a>
            <ImportCsvButton defaultType="topic" />
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} /> New topic
            </Button>
          </>
        }
      />
      <div className="mb-4 flex items-center gap-3">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="!w-40">
          <option value="">Any status</option>
          {TOPIC_STATUSES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </Select>
        {(topics?.length ?? 0) > 0 && (
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] text-slate-600 dark:text-slate-300">
            <SelectCheckbox
              checked={Boolean(topics?.length) && topics!.every((t) => selection.selected.has(t.id))}
              indeterminate={topics?.some((t) => selection.selected.has(t.id))}
              onChange={() => selection.toggleAll((topics ?? []).map((t) => t.id as Id))}
              label="Select all topics"
            />
            Select all
          </label>
        )}
      </div>

      {isLoading ? (
        <Spinner />
      ) : !topics?.length ? (
        <EmptyState title="No topics yet" hint="Capture anything that will need airtime in a management meeting — Fulcrum will suggest when to schedule it." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {topics.map((topic) => (
            <button
              key={topic.id}
              onClick={() => setSelectedId(topic.id)}
              className={cn(
                'rounded-xl border bg-white p-4 text-left shadow-sm transition-colors hover:border-indigo-300 dark:bg-slate-900 dark:hover:border-indigo-700',
                selection.selected.has(topic.id)
                  ? 'border-indigo-400 dark:border-indigo-600'
                  : 'border-slate-200 dark:border-slate-800',
              )}
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <span className="flex min-w-0 items-start gap-2">
                  <span className="mt-0.5">
                    <SelectCheckbox
                      checked={selection.selected.has(topic.id)}
                      onChange={() => selection.toggle(topic.id)}
                      label={`Select ${topic.title}`}
                    />
                  </span>
                  <span className="text-[13px] leading-snug font-semibold">{topic.title}</span>
                </span>
                <StatusBadge status={topic.status} />
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <IntentBadge intent={topic.intent} />
                <Badge tone={topic.readiness === 'ready' ? 'green' : 'slate'}>{topic.readiness}</Badge>
                <Badge tone="slate">{topic.duration_minutes} min</Badge>
                {topic.recurring && <Badge tone="amber">recurring</Badge>}
                {topic.target_by && <Badge tone={dueTone(topic.target_by)}>by {fmtDate(topic.target_by)}</Badge>}
              </div>
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                {topic.sponsor?.name ?? 'No sponsor'}
                {topic.workstream ? ` · ${topic.workstream.name}` : ''}
              </div>
            </button>
          ))}
        </div>
      )}

      <BulkBar type="topic" ids={[...selection.selected]} onClear={selection.clear} />

      {selectedId && (
        <TopicDrawer key={selectedId} id={selectedId} onClose={() => setSelectedId(null)} people={people} workstreams={workstreams} />
      )}
      <CreateTopicModal open={creating} onClose={() => setCreating(false)} people={people} workstreams={workstreams} />
    </div>
  )
}

function TopicDrawer({ id, onClose, people, workstreams }: { id: number; onClose: () => void; people: Person[]; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const { data: topics = [] } = useQuery({ queryKey: ['topics', ''], queryFn: () => api.get<Topic[]>('/topics') })
  const { data: commitments = [] } = useQuery({ queryKey: ['commitments', 'all-open'], queryFn: () => api.get<Commitment[]>('/commitments?open_only=true') })
  const item = topics.find((t) => t.id === id)

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/topics/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['topics'] }),
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/topics/${id}`),
    onSuccess: () => {
      toast.success('Topic deleted')
      onClose()
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
  })

  if (!item) return null
  return (
    <Drawer open onClose={onClose} title={item.title}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Intent">
          <Select value={item.intent} onChange={(e) => patch.mutate({ intent: e.target.value })}>
            {INTENTS.map((i) => (
              <option key={i}>{i}</option>
            ))}
          </Select>
        </Field>
        <Field label="Duration (min)">
          <Input
            type="number"
            defaultValue={item.duration_minutes}
            onBlur={(e) => patch.mutate({ duration_minutes: Number(e.target.value) || 15 })}
          />
        </Field>
        <Field label="Readiness">
          <Select value={item.readiness} onChange={(e) => patch.mutate({ readiness: e.target.value })}>
            <option value="draft">draft</option>
            <option value="ready">ready</option>
          </Select>
        </Field>
        <Field label="Status">
          <Select value={item.status} onChange={(e) => patch.mutate({ status: e.target.value })}>
            {TOPIC_STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <Field label="Recurring (standing item)">
          <Select
            value={item.recurring ? 'yes' : 'no'}
            onChange={(e) => patch.mutate({ recurring: e.target.value === 'yes' })}
            title="Recurring topics stay available as agenda candidates for every meeting"
          >
            <option value="no">No — one-off</option>
            <option value="yes">Yes — reusable every meeting</option>
          </Select>
        </Field>
        <Field label="Sponsor">
          <Select value={item.sponsor?.id ?? ''} onChange={(e) => patch.mutate({ sponsor_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">None</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Target by">
          <Input type="date" value={item.target_by ?? ''} onChange={(e) => patch.mutate({ target_by: e.target.value || null })} />
        </Field>
        <Field label="Workstream">
          <Select value={item.workstream?.id ?? ''} onChange={(e) => patch.mutate({ workstream_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">None</option>
            {workstreams.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Linked commitment">
          <Select value={item.commitment?.id ?? ''} onChange={(e) => patch.mutate({ commitment_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">None</option>
            {commitments.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Description / intent detail">
        <Textarea
          rows={3}
          defaultValue={item.description ?? ''}
          onBlur={(e) => e.target.value !== (item.description ?? '') && patch.mutate({ description: e.target.value || null })}
        />
      </Field>
      <Field label="Papers link (SharePoint etc.)">
        <Input
          defaultValue={item.papers_url ?? ''}
          onBlur={(e) => e.target.value !== (item.papers_url ?? '') && patch.mutate({ papers_url: e.target.value || null })}
          placeholder="https://…"
        />
      </Field>
      <LinkPanel entityType="topic" entityId={id} />
      <Section title="Danger zone">
        <Button variant="danger" size="sm" onClick={() => remove.mutate()}>
          Delete topic
        </Button>
      </Section>
    </Drawer>
  )
}

function CreateTopicModal({ open, onClose, people, workstreams }: { open: boolean; onClose: () => void; people: Person[]; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const create = useMutation({
    mutationFn: () =>
      api.post('/topics', {
        title: form.title,
        description: form.description || null,
        intent: form.intent || 'inform',
        duration_minutes: Number(form.duration_minutes) || 15,
        sponsor_id: form.sponsor_id ? Number(form.sponsor_id) : null,
        workstream_id: form.workstream_id ? Number(form.workstream_id) : null,
        readiness: form.readiness || 'draft',
        target_by: form.target_by || null,
        recurring: form.recurring === 'yes',
      }),
    onSuccess: () => {
      toast.success('Topic created')
      setForm({})
      onClose()
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open={open} onClose={onClose} title="New topic">
      <div className="space-y-3">
        <Field label="Title">
          <Input value={form.title ?? ''} onChange={set('title')} autoFocus placeholder="What needs discussing?" />
        </Field>
        <Field label="Description">
          <Textarea rows={2} value={form.description ?? ''} onChange={set('description')} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Intent">
            <Select value={form.intent ?? 'inform'} onChange={set('intent')}>
              {INTENTS.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </Select>
          </Field>
          <Field label="Duration (min)">
            <Input type="number" value={form.duration_minutes ?? '15'} onChange={set('duration_minutes')} />
          </Field>
          <Field label="Sponsor">
            <Select value={form.sponsor_id ?? ''} onChange={set('sponsor_id')}>
              <option value="">None</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
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
          <Field label="Readiness">
            <Select value={form.readiness ?? 'draft'} onChange={set('readiness')}>
              <option value="draft">draft</option>
              <option value="ready">ready</option>
            </Select>
          </Field>
          <Field label="Target by">
            <Input type="date" value={form.target_by ?? ''} onChange={set('target_by')} />
          </Field>
          <Field label="Recurring (standing item)">
            <Select value={form.recurring ?? 'no'} onChange={set('recurring')}>
              <option value="no">No — one-off</option>
              <option value="yes">Yes — reusable every meeting</option>
            </Select>
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!form.title} onClick={() => create.mutate()}>
            Create
          </Button>
        </div>
      </div>
    </Modal>
  )
}
