import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, X } from 'lucide-react'
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
          <Button onClick={() => setCreating(true)}>
            <Plus size={15} /> New {tab === 'people' ? 'person' : 'workstream'}
          </Button>
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

  if (isLoading) return <Spinner />
  if (!people?.length)
    return <EmptyState title="No people yet" hint="Add your principal, BPMs, directors — anyone who owns actions or sponsors topics." />

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
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
              <tr key={person.id} className={cn(!person.active && 'opacity-50')}>
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
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <PersonModal person={editing} onClose={() => setEditing(null)} />}
    </>
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
        <div key={ws.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-[13px] font-semibold">
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
