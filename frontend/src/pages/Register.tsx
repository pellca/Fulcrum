import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { CopyCopilotPromptButton, ImportCsvButton } from '../components/CsvImport'
import { BulkBar, SelectAllHeader, SelectCheckbox, useSelection, type Id } from '../components/BulkSelect'
import { api, type Action, type Commitment, type Person, type Workstream } from '../api'
import {
  Badge,
  Button,
  cn,
  dueTone,
  EmptyState,
  Field,
  fmtDate,
  Input,
  Modal,
  PageHeader,
  priorityTone,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
} from '../components/ui'
import { ChasePanel, Drawer, LinkPanel, Section } from '../components/panels'

const ACTION_STATUSES = ['todo', 'in_progress', 'blocked', 'done', 'cancelled']
const COMMITMENT_STATUSES = ['open', 'on_track', 'at_risk', 'delivered', 'dropped']
const ORIGINS = ['principal', 'aet', 'external', 'self']

type Tab = 'actions' | 'commitments'

export default function Register() {
  const [tab, setTab] = useState<Tab>('actions')
  const [filters, setFilters] = useState({ status: '', owner_id: '', workstream_id: '', origin: '', openOnly: true })
  const [selected, setSelected] = useState<{ kind: Tab; id: number } | null>(null)
  const [creating, setCreating] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const selection = useSelection()

  // deep links: ?open=action-12 opens a drawer; ?owner=3 / ?workstream=2 pre-filter
  useEffect(() => {
    const open = searchParams.get('open')
    const owner = searchParams.get('owner')
    const workstream = searchParams.get('workstream')
    if (!open && !owner && !workstream) return
    if (open) {
      const [kind, rawId] = open.split('-')
      const id = Number(rawId)
      if ((kind === 'action' || kind === 'commitment') && id) {
        const tabKind: Tab = kind === 'action' ? 'actions' : 'commitments'
        setTab(tabKind)
        setSelected({ kind: tabKind, id })
      }
    }
    if (owner || workstream)
      setFilters((f) => ({ ...f, owner_id: owner ?? f.owner_id, workstream_id: workstream ?? f.workstream_id }))
    setSearchParams({}, { replace: true })
  }, [searchParams, setSearchParams])

  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const { data: workstreams = [] } = useQuery({ queryKey: ['workstreams'], queryFn: () => api.get<Workstream[]>('/workstreams') })

  const params = useMemo(() => {
    const p = new URLSearchParams()
    if (filters.status) p.set('status', filters.status)
    if (filters.owner_id) p.set('owner_id', filters.owner_id)
    if (filters.workstream_id) p.set('workstream_id', filters.workstream_id)
    if (tab === 'commitments' && filters.origin) p.set('origin', filters.origin)
    if (filters.openOnly && !filters.status) p.set('open_only', 'true')
    return p.toString()
  }, [filters, tab])

  const { data: actions, isLoading: loadingActions } = useQuery({
    queryKey: ['actions', params],
    queryFn: () => api.get<Action[]>(`/actions?${params}`),
    enabled: tab === 'actions',
  })
  const { data: commitments, isLoading: loadingCommitments } = useQuery({
    queryKey: ['commitments', params],
    queryFn: () => api.get<Commitment[]>(`/commitments?${params}`),
    enabled: tab === 'commitments',
  })

  const statuses = tab === 'actions' ? ACTION_STATUSES : COMMITMENT_STATUSES
  const loading = tab === 'actions' ? loadingActions : loadingCommitments

  return (
    <div>
      <PageHeader
        title="Register"
        subtitle="Every action and commitment, who owns it, and when it lands"
        actions={
          <>
            <CopyCopilotPromptButton />
            <ImportCsvButton />
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} /> New {tab === 'actions' ? 'action' : 'commitment'}
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="mr-2 flex rounded-lg border border-slate-200 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900">
          {(['actions', 'commitments'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => {
                setTab(t)
                setFilters((f) => ({ ...f, status: '', origin: '' }))
                selection.clear()
              }}
              className={cn(
                'rounded-md px-3 py-1.5 text-[13px] font-medium capitalize transition-colors',
                tab === t ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <Select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} className="!w-36">
          <option value="">Any status</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s.replace('_', ' ')}
            </option>
          ))}
        </Select>
        <Select value={filters.owner_id} onChange={(e) => setFilters((f) => ({ ...f, owner_id: e.target.value }))} className="!w-40">
          <option value="">Any owner</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <Select value={filters.workstream_id} onChange={(e) => setFilters((f) => ({ ...f, workstream_id: e.target.value }))} className="!w-44">
          <option value="">Any workstream</option>
          {workstreams.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
        {tab === 'commitments' && (
          <Select value={filters.origin} onChange={(e) => setFilters((f) => ({ ...f, origin: e.target.value }))} className="!w-36">
            <option value="">Any origin</option>
            {ORIGINS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        )}
        <label className="flex items-center gap-1.5 text-[13px] text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={filters.openOnly}
            onChange={(e) => setFilters((f) => ({ ...f, openOnly: e.target.checked }))}
            className="rounded accent-indigo-600"
          />
          Open only
        </label>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <ItemTable
          rows={(tab === 'actions' ? actions : commitments) ?? []}
          kind={tab}
          onSelect={(id) => setSelected({ kind: tab, id })}
          selection={selection}
        />
      )}

      <BulkBar
        type={tab === 'actions' ? 'action' : 'commitment'}
        ids={[...selection.selected]}
        onClear={selection.clear}
      />

      {selected?.kind === 'actions' && (
        <ActionDrawer
          key={selected.id}
          id={selected.id}
          onClose={() => setSelected(null)}
          onConverted={(id) => {
            setTab('commitments')
            setSelected({ kind: 'commitments', id })
          }}
          people={people}
          workstreams={workstreams}
        />
      )}
      {selected?.kind === 'commitments' && (
        <CommitmentDrawer
          key={selected.id}
          id={selected.id}
          onClose={() => setSelected(null)}
          onConverted={(id) => {
            setTab('actions')
            setSelected({ kind: 'actions', id })
          }}
          people={people}
          workstreams={workstreams}
        />
      )}
      <CreateModal open={creating} onClose={() => setCreating(false)} kind={tab} people={people} workstreams={workstreams} />
    </div>
  )
}

function ItemTable({
  rows,
  kind,
  onSelect,
  selection,
}: {
  rows: (Action | Commitment)[]
  kind: Tab
  onSelect: (id: number) => void
  selection: ReturnType<typeof useSelection>
}) {
  if (rows.length === 0)
    return (
      <EmptyState
        title={`No ${kind} match these filters`}
        hint="Use the quick-add bar at the top (Ctrl+K) to capture items as you hear them."
      />
    )
  const ids: Id[] = rows.map((row) => row.id)
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <th className="w-8 px-3 py-2.5">
              <SelectAllHeader ids={ids} selected={selection.selected} onToggleAll={selection.toggleAll} />
            </th>
            <th className="px-4 py-2.5 font-medium">Title</th>
            <th className="px-3 py-2.5 font-medium">Owner</th>
            <th className="px-3 py-2.5 font-medium">Workstream</th>
            {kind === 'commitments' && <th className="px-3 py-2.5 font-medium">Origin</th>}
            <th className="px-3 py-2.5 font-medium">Due</th>
            <th className="px-3 py-2.5 font-medium">Status</th>
            <th className="px-3 py-2.5 font-medium">Priority</th>
            <th className="px-3 py-2.5 font-medium">Chase</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50 dark:divide-slate-800/60">
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onSelect(row.id)}
              className={cn(
                'cursor-pointer transition-colors hover:bg-indigo-50/50 dark:hover:bg-indigo-950/20',
                selection.selected.has(row.id) && 'bg-indigo-50/70 dark:bg-indigo-950/30',
              )}
            >
              <td className="px-3 py-2.5">
                <SelectCheckbox
                  checked={selection.selected.has(row.id)}
                  onChange={() => selection.toggle(row.id)}
                  label={`Select ${row.title}`}
                />
              </td>
              <td className="max-w-md truncate px-4 py-2.5 font-medium">{row.title}</td>
              <td className="px-3 py-2.5 whitespace-nowrap text-slate-600 dark:text-slate-300">{row.owner?.name ?? '—'}</td>
              <td className="px-3 py-2.5 whitespace-nowrap">
                {row.workstream ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: row.workstream.colour }} />
                    {row.workstream.name}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              {kind === 'commitments' && <td className="px-3 py-2.5">{(row as Commitment).origin}</td>}
              <td className="px-3 py-2.5 whitespace-nowrap">
                <Badge tone={dueTone(row.due_date, ['done', 'cancelled', 'delivered', 'dropped'].includes(row.status))}>
                  {fmtDate(row.due_date)}
                </Badge>
              </td>
              <td className="px-3 py-2.5">
                <StatusBadge status={row.status} />
              </td>
              <td className="px-3 py-2.5">
                <Badge tone={priorityTone[row.priority]}>{row.priority}</Badge>
              </td>
              <td className="px-3 py-2.5 whitespace-nowrap text-xs text-slate-500">
                {row.next_chase_on ? fmtDate(row.next_chase_on) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ActionDrawer({ id, onClose, onConverted, people, workstreams }: { id: number; onClose: () => void; onConverted: (id: number) => void; people: Person[]; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const [convertOrigin, setConvertOrigin] = useState('principal')
  const { data: item } = useQuery({ queryKey: ['action', id], queryFn: () => api.get<Action>(`/actions/${id}`) })
  const { data: commitments = [] } = useQuery({ queryKey: ['commitments', 'all-open'], queryFn: () => api.get<Commitment[]>('/commitments?open_only=true') })

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/actions/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['action', id] })
      queryClient.invalidateQueries({ queryKey: ['actions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/actions/${id}`),
    onSuccess: () => {
      toast.success('Action deleted')
      onClose()
      queryClient.invalidateQueries({ queryKey: ['actions'] })
    },
  })
  const convert = useMutation({
    mutationFn: () => api.post<Commitment>(`/actions/${id}/convert`, { origin: convertOrigin }),
    onSuccess: (commitment) => {
      toast.success('Converted to commitment', { description: 'Chases, links and history moved with it.' })
      queryClient.invalidateQueries()
      onConverted(commitment.id)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (!item) return null
  return (
    <Drawer open onClose={onClose} title={item.title}>
      <Field label="Title">
        <Input
          defaultValue={item.title}
          onBlur={(e) => {
            const value = e.target.value.trim()
            if (value && value !== item.title) patch.mutate({ title: value })
          }}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Status">
          <Select value={item.status} onChange={(e) => patch.mutate({ status: e.target.value })}>
            {ACTION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Priority">
          <Select value={item.priority} onChange={(e) => patch.mutate({ priority: e.target.value })}>
            {['high', 'medium', 'low'].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </Select>
        </Field>
        <Field label="Owner">
          <Select value={item.owner?.id ?? ''} onChange={(e) => patch.mutate({ owner_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Unowned</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Due date">
          <Input type="date" value={item.due_date ?? ''} onChange={(e) => patch.mutate({ due_date: e.target.value || null })} />
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
        <Field label="Delivers commitment">
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
      <Field label="Notes">
        <Textarea
          rows={3}
          defaultValue={item.notes ?? ''}
          onBlur={(e) => e.target.value !== (item.notes ?? '') && patch.mutate({ notes: e.target.value || null })}
          placeholder="Context, latest position…"
        />
      </Field>
      <ChasePanel kind="action" itemId={id} />
      <LinkPanel entityType="action" entityId={id} />
      <Section title="Convert">
        <div className="flex items-end gap-2">
          <div className="w-44">
            <Field label="Owed to (origin)">
              <Select value={convertOrigin} onChange={(e) => setConvertOrigin(e.target.value)}>
                {ORIGINS.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Button variant="secondary" size="sm" onClick={() => convert.mutate()} disabled={convert.isPending}>
            Make this a commitment
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-slate-400">
          Chases, links and history move across; status maps (blocked → at risk, done → delivered).
        </p>
      </Section>
      <Section title="Danger zone">
        <Button variant="danger" size="sm" onClick={() => remove.mutate()}>
          Delete action
        </Button>
      </Section>
    </Drawer>
  )
}

function CommitmentDrawer({ id, onClose, onConverted, people, workstreams }: { id: number; onClose: () => void; onConverted: (id: number) => void; people: Person[]; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const { data: item } = useQuery({ queryKey: ['commitment', id], queryFn: () => api.get<Commitment>(`/commitments/${id}`) })
  const { data: linkedActions = [] } = useQuery({
    queryKey: ['actions', 'for-commitment', id],
    queryFn: () => api.get<Action[]>(`/actions?commitment_id=${id}`),
  })

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/commitments/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commitment', id] })
      queryClient.invalidateQueries({ queryKey: ['commitments'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/commitments/${id}`),
    onSuccess: () => {
      toast.success('Commitment deleted')
      onClose()
      queryClient.invalidateQueries({ queryKey: ['commitments'] })
    },
  })
  const convert = useMutation({
    mutationFn: () => api.post<Action>(`/commitments/${id}/convert`),
    onSuccess: (action) => {
      toast.success('Converted to action', { description: 'Chases, links and history moved with it.' })
      queryClient.invalidateQueries()
      onConverted(action.id)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (!item) return null
  return (
    <Drawer open onClose={onClose} title={item.title}>
      <Field label="Title">
        <Input
          defaultValue={item.title}
          onBlur={(e) => {
            const value = e.target.value.trim()
            if (value && value !== item.title) patch.mutate({ title: value })
          }}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Status">
          <Select value={item.status} onChange={(e) => patch.mutate({ status: e.target.value })}>
            {COMMITMENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Priority">
          <Select value={item.priority} onChange={(e) => patch.mutate({ priority: e.target.value })}>
            {['high', 'medium', 'low'].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </Select>
        </Field>
        <Field label="Owner">
          <Select value={item.owner?.id ?? ''} onChange={(e) => patch.mutate({ owner_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Unowned</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Due date">
          <Input type="date" value={item.due_date ?? ''} onChange={(e) => patch.mutate({ due_date: e.target.value || null })} />
        </Field>
        <Field label="Origin">
          <Select value={item.origin} onChange={(e) => patch.mutate({ origin: e.target.value })}>
            {ORIGINS.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </Select>
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
      </div>
      <Field label="Description">
        <Textarea
          rows={3}
          defaultValue={item.description ?? ''}
          onBlur={(e) => e.target.value !== (item.description ?? '') && patch.mutate({ description: e.target.value || null })}
          placeholder="What exactly was promised, to whom?"
        />
      </Field>
      <Section title={`Delivery actions (${linkedActions.length})`}>
        {linkedActions.length === 0 ? (
          <p className="text-xs text-slate-400">No actions attached to this commitment yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {linkedActions.map((action) => (
              <li key={action.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
                <span className="min-w-0 truncate font-medium">{action.title}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <StatusBadge status={action.status} />
                  <Badge tone={dueTone(action.due_date)}>{fmtDate(action.due_date)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <ChasePanel kind="commitment" itemId={id} />
      <LinkPanel entityType="commitment" entityId={id} />
      <Section title="Convert">
        <Button variant="secondary" size="sm" onClick={() => convert.mutate()} disabled={convert.isPending}>
          Make this an action
        </Button>
        <p className="mt-1.5 text-xs text-slate-400">
          Chases, links and history move across; status maps back (at risk → blocked). Any delivery
          actions and linked topics stay connected via <em>relates</em> links.
        </p>
      </Section>
      <Section title="Danger zone">
        <Button variant="danger" size="sm" onClick={() => remove.mutate()}>
          Delete commitment
        </Button>
      </Section>
    </Drawer>
  )
}

function CreateModal({ open, onClose, kind, people, workstreams }: { open: boolean; onClose: () => void; kind: Tab; people: Person[]; workstreams: Workstream[] }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const create = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        title: form.title,
        description: form.description || null,
        owner_id: form.owner_id ? Number(form.owner_id) : null,
        workstream_id: form.workstream_id ? Number(form.workstream_id) : null,
        due_date: form.due_date || null,
        priority: form.priority || 'medium',
      }
      if (kind === 'commitments') body.origin = form.origin || 'principal'
      return api.post(kind === 'commitments' ? '/commitments' : '/actions', body)
    },
    onSuccess: () => {
      toast.success('Created')
      setForm({})
      onClose()
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open={open} onClose={onClose} title={`New ${kind === 'commitments' ? 'commitment' : 'action'}`}>
      <div className="space-y-3">
        <Field label="Title">
          <Input value={form.title ?? ''} onChange={set('title')} placeholder="What needs to happen?" autoFocus />
        </Field>
        <Field label="Description">
          <Textarea rows={2} value={form.description ?? ''} onChange={set('description')} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner">
            <Select value={form.owner_id ?? ''} onChange={set('owner_id')}>
              <option value="">Unowned</option>
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
          <Field label="Due date">
            <Input type="date" value={form.due_date ?? ''} onChange={set('due_date')} />
          </Field>
          <Field label="Priority">
            <Select value={form.priority ?? 'medium'} onChange={set('priority')}>
              {['high', 'medium', 'low'].map((p) => (
                <option key={p}>{p}</option>
              ))}
            </Select>
          </Field>
          {kind === 'commitments' && (
            <Field label="Origin">
              <Select value={form.origin ?? 'principal'} onChange={set('origin')}>
                {ORIGINS.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </Select>
            </Field>
          )}
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
