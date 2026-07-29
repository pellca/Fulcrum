import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, Download, NotebookTabs, Plus, Trash2, X } from 'lucide-react'
import { PeopleImportButton } from '../components/PeopleImport'
import { BulkBar, SelectAllHeader, SelectCheckbox, useSelection, type Id } from '../components/BulkSelect'
import { api, type Person, type Workstream } from '../api'
import {
  Badge,
  Button,
  cn,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
} from '../components/ui'

type Tab = 'people' | 'workstreams'

export default function People() {
  const [tab, setTab] = useState<Tab>('people')
  const [creating, setCreating] = useState(false)

  return (
    <div>
      <PageHeader
        title="People & workstreams"
        subtitle="Who owns things, and the streams of work they sit in"
        actions={
          <>
            {tab === 'people' && (
              <>
                <a href="/api/imports/templates/people" download>
                  <Button variant="ghost" title="Download the CSV template for people">
                    <Download size={15} /> Template
                  </Button>
                </a>
                <PeopleImportButton />
              </>
            )}
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} /> New {tab === 'people' ? 'person' : 'workstream'}
            </Button>
          </>
        }
      />
      <div className="mb-4 flex rounded-lg border border-slate-200 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900" style={{ width: 'fit-content' }}>
        {(['people', 'workstreams'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[13px] font-medium capitalize transition-colors',
              tab === t ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === 'people' ? <PeopleTable /> : <WorkstreamTable />}
      {creating && tab === 'people' && <PersonModal onClose={() => setCreating(false)} />}
      {creating && tab === 'workstreams' && <WorkstreamModal onClose={() => setCreating(false)} />}
    </div>
  )
}

function PeopleTable() {
  const queryClient = useQueryClient()
  const selection = useSelection()
  const { data: people, isLoading } = useQuery({
    queryKey: ['people', 'all'],
    queryFn: () => api.get<Person[]>('/people?include_inactive=true'),
  })
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/people/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['people'] }),
  })
  const removeAlias = useMutation({
    mutationFn: (aliasId: number) => api.delete(`/people/aliases/${aliasId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['people'] }),
  })
  const [editing, setEditing] = useState<Person | null>(null)
  const [deleting, setDeleting] = useState<Person | null>(null)

  if (isLoading) return <Spinner />
  if (!people?.length)
    return <EmptyState title="No people yet" hint="Add your principal, BPMs, directors — anyone who owns actions or sponsors topics." />

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <th className="w-8 px-3 py-2.5">
                <SelectAllHeader
                  ids={people.map((p) => p.id as Id)}
                  selected={selection.selected}
                  onToggleAll={selection.toggleAll}
                />
              </th>
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-3 py-2.5 font-medium">Role</th>
              <th className="px-3 py-2.5 font-medium">Team</th>
              <th className="px-3 py-2.5 font-medium">Aliases</th>
              <th className="px-3 py-2.5 font-medium">Flags</th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50 dark:divide-slate-800/60">
            {people.map((person) => (
              <tr
                key={person.id}
                className={cn(
                  !person.active && 'opacity-50',
                  selection.selected.has(person.id) && 'bg-indigo-50/70 dark:bg-indigo-950/30',
                )}
              >
                <td className="px-3 py-2.5">
                  <SelectCheckbox
                    checked={selection.selected.has(person.id)}
                    onChange={() => selection.toggle(person.id)}
                    label={`Select ${person.name}`}
                  />
                </td>
                <td className="px-4 py-2.5 font-medium">{person.name}</td>
                <td className="px-3 py-2.5 text-slate-600 dark:text-slate-300">{person.role ?? '—'}</td>
                <td className="px-3 py-2.5 text-slate-600 dark:text-slate-300">{person.team ?? '—'}</td>
                <td className="px-3 py-2.5">
                  <span className="flex flex-wrap gap-1">
                    {person.aliases.map((alias) => (
                      <Badge key={alias.id} tone="slate">
                        {alias.alias}
                        <button onClick={() => removeAlias.mutate(alias.id)} className="ml-0.5 hover:text-rose-500">
                          <X size={10} />
                        </button>
                      </Badge>
                    ))}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {person.is_bpm && <Badge tone="indigo">BPM</Badge>}
                  {!person.active && <Badge tone="slate">inactive</Badge>}
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <Link to={`/people/${person.id}/pack`}>
                    <Button size="sm" variant="ghost" title="Everything they own — prep for a 1:1">
                      <NotebookTabs size={13} /> 1:1 pack
                    </Button>
                  </Link>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(person)}>
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => patch.mutate({ id: person.id, body: { active: !person.active } })}
                  >
                    {person.active ? 'Deactivate' : 'Reactivate'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeleting(person)}
                    className="!text-rose-500 hover:!bg-rose-50 dark:hover:!bg-rose-950/40"
                    title="Delete permanently"
                  >
                    <Trash2 size={13} />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <PersonModal person={editing} onClose={() => setEditing(null)} />}
      {deleting && <DeletePersonModal person={deleting} onClose={() => setDeleting(null)} />}
      <BulkBar type="person" ids={[...selection.selected]} onClear={selection.clear} />
    </>
  )
}

function DeletePersonModal({ person, onClose }: { person: Person; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: refs, isLoading } = useQuery({
    queryKey: ['person-refs', person.id],
    queryFn: () => api.get<{ warnings: { label: string; count: number; examples: string[] }[] }>(
      `/people/${person.id}/references`,
    ),
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/people/${person.id}`),
    onSuccess: () => {
      toast.success(`${person.name} deleted`)
      onClose()
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open onClose={onClose} title={`Delete ${person.name}?`}>
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {refs?.warnings.length ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-amber-800 dark:text-amber-300">
                <AlertTriangle size={13} /> They still own things:
              </p>
              <ul className="space-y-1 text-xs">
                {refs.warnings.map((warning) => (
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
              <p className="mt-2 text-[11px] text-amber-800 dark:text-amber-300">
                Those items are <strong>not</strong> deleted — they stay in the register but become unowned.
                Deactivating instead keeps the ownership history intact.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Nothing references {person.name} — safe to delete.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
              Delete permanently
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function PersonModal({ person, onClose }: { person?: Person; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({
    name: person?.name ?? '',
    email: person?.email ?? '',
    team: person?.team ?? '',
    role: person?.role ?? '',
    is_bpm: person?.is_bpm ? 'true' : 'false',
  })
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        email: form.email || null,
        team: form.team || null,
        role: form.role || null,
        is_bpm: form.is_bpm === 'true',
      }
      return person ? api.patch(`/people/${person.id}`, body) : api.post('/people', body)
    },
    onSuccess: () => {
      toast.success(person ? 'Person updated' : 'Person added')
      onClose()
      queryClient.invalidateQueries({ queryKey: ['people'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open onClose={onClose} title={person ? `Edit ${person.name}` : 'New person'}>
      <div className="space-y-3">
        <Field label="Name">
          <Input value={form.name} onChange={set('name')} autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <Input value={form.role} onChange={set('role')} placeholder="Audit Director" />
          </Field>
          <Field label="Team">
            <Input value={form.team} onChange={set('team')} />
          </Field>
          <Field label="Email">
            <Input value={form.email} onChange={set('email')} />
          </Field>
          <Field label="Business manager (BPM)?">
            <Select value={form.is_bpm} onChange={set('is_bpm')}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </Select>
          </Field>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!form.name} onClick={() => save.mutate()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function WorkstreamTable() {
  const queryClient = useQueryClient()
  const selection = useSelection()
  const { data: workstreams, isLoading } = useQuery({
    queryKey: ['workstreams', 'all'],
    queryFn: () => api.get<Workstream[]>('/workstreams?include_closed=true'),
  })
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/workstreams/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workstreams'] }),
  })

  if (isLoading) return <Spinner />
  if (!workstreams?.length)
    return <EmptyState title="No workstreams" hint="Audits, investigations, initiatives, governance cycles — the lanes your work runs in." />

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {workstreams.map((ws) => (
        <div
          key={ws.id}
          className={cn(
            'rounded-xl border bg-white p-4 shadow-sm dark:bg-slate-900',
            selection.selected.has(ws.id)
              ? 'border-indigo-400 dark:border-indigo-600'
              : 'border-slate-200 dark:border-slate-800',
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-[13px] font-semibold">
              <SelectCheckbox
                checked={selection.selected.has(ws.id)}
                onChange={() => selection.toggle(ws.id)}
                label={`Select ${ws.name}`}
              />
              <span className="h-3 w-3 rounded-full" style={{ background: ws.colour }} />
              {ws.name}
            </span>
            <Badge tone={ws.status === 'active' ? 'green' : 'slate'}>{ws.status}</Badge>
          </div>
          <div className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
            {ws.category} · {ws.owner?.name ?? 'no owner'}
          </div>
          <div className="mt-3 flex gap-1.5">
            {ws.status === 'active' ? (
              <Button size="sm" variant="secondary" onClick={() => patch.mutate({ id: ws.id, body: { status: 'closed' } })}>
                Close
              </Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => patch.mutate({ id: ws.id, body: { status: 'active' } })}>
                Reopen
              </Button>
            )}
          </div>
        </div>
      ))}
      <BulkBar type="workstream" ids={[...selection.selected]} onClear={selection.clear} />
    </div>
  )
}

function WorkstreamModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const [form, setForm] = useState<Record<string, string>>({ colour: '#6366f1', category: 'initiative' })
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const create = useMutation({
    mutationFn: () =>
      api.post('/workstreams', {
        name: form.name,
        category: form.category,
        colour: form.colour,
        owner_id: form.owner_id ? Number(form.owner_id) : null,
      }),
    onSuccess: () => {
      toast.success('Workstream created')
      onClose()
      queryClient.invalidateQueries({ queryKey: ['workstreams'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal open onClose={onClose} title="New workstream">
      <div className="space-y-3">
        <Field label="Name">
          <Input value={form.name ?? ''} onChange={set('name')} autoFocus placeholder="e.g. Credit Risk Audit" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select value={form.category} onChange={set('category')}>
              <option value="audit">audit</option>
              <option value="investigation">investigation</option>
              <option value="initiative">initiative</option>
              <option value="governance">governance</option>
            </Select>
          </Field>
          <Field label="Owner">
            <Select value={form.owner_id ?? ''} onChange={set('owner_id')}>
              <option value="">None</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Colour">
            <Input type="color" value={form.colour} onChange={set('colour')} className="!h-9 !p-1" />
          </Field>
        </div>
        <div className="flex justify-end gap-2">
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
