import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { AlertTriangle, Check, Download, GripVertical, NotebookTabs, Pencil, Plus, StickyNote, Trash2, X } from 'lucide-react'
import { PeopleImportButton } from '../components/PeopleImport'
import { BulkBar, SelectAllHeader, SelectCheckbox, useSelection, type Id } from '../components/BulkSelect'
import {
  api,
  createPersonNote,
  deletePersonNote,
  listPersonNotes,
  updatePersonNote,
  type Person,
  type PersonNote,
  type PersonNoteKind,
  type PersonNotePatch,
  type Workstream,
} from '../api'
import {
  Badge,
  Button,
  cn,
  EmptyState,
  Field,
  fmtDate,
  Input,
  Modal,
  MultiSelect,
  PageHeader,
  peopleLabel,
  Select,
  Spinner,
  Textarea,
} from '../components/ui'
import { Drawer, Section } from '../components/panels'

const NOTE_KINDS: PersonNoteKind[] = ['feedback', 'call', 'observation', 'general']
const noteKindTone: Record<PersonNoteKind, string> = {
  feedback: 'violet',
  call: 'blue',
  observation: 'amber',
  general: 'slate',
}

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
  const [notesFor, setNotesFor] = useState<Person | null>(null)

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
                  <span className="flex flex-wrap gap-1">
                    {person.is_bpm && <Badge tone="indigo">BPM</Badge>}
                    {person.pin_discussion && <Badge tone="violet">Pinned to Today</Badge>}
                    {!person.active && <Badge tone="slate">inactive</Badge>}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <Link to={`/people/${person.id}/pack`}>
                    <Button size="sm" variant="ghost" title="Everything they own — prep for a 1:1">
                      <NotebookTabs size={13} /> 1:1 pack
                    </Button>
                  </Link>
                  <Button size="sm" variant="ghost" onClick={() => setNotesFor(person)} title="Feedback, calls, observations">
                    <StickyNote size={13} /> Notes
                  </Button>
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
      {notesFor && <PersonNotesDrawer person={notesFor} onClose={() => setNotesFor(null)} />}
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

function PersonNotesDrawer({ person, onClose }: { person: Person; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [kindFilter, setKindFilter] = useState<PersonNoteKind | ''>('')
  const [newKind, setNewKind] = useState<PersonNoteKind>('general')
  const [newNote, setNewNote] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editKind, setEditKind] = useState<PersonNoteKind>('general')
  const [editText, setEditText] = useState('')

  const { data: notes = [], isLoading } = useQuery({
    queryKey: ['person-notes', person.id, kindFilter],
    queryFn: () => listPersonNotes(person.id, kindFilter ? { kind: kindFilter } : undefined),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['person-notes', person.id] })

  const add = useMutation({
    mutationFn: () => createPersonNote(person.id, { kind: newKind, note: newNote.trim() }),
    onSuccess: () => {
      setNewNote('')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: PersonNotePatch }) => updatePersonNote(id, body),
    onSuccess: () => {
      setEditingId(null)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deletePersonNote(id),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  })

  const submitNew = () => {
    if (!newNote.trim() || add.isPending) return
    add.mutate()
  }

  const startEdit = (note: PersonNote) => {
    setEditingId(note.id)
    setEditKind(note.kind)
    setEditText(note.note)
  }

  const saveEdit = (id: number) => {
    if (!editText.trim()) return
    update.mutate({ id, body: { kind: editKind, note: editText.trim() } })
  }

  const toggleDiscussed = (note: PersonNote) =>
    update.mutate({ id: note.id, body: { discussed_on: note.discussed_on ? null : new Date().toISOString().slice(0, 10) } })

  return (
    <Drawer open onClose={onClose} title={`Notes — ${person.name}`}>
      <Section title="Log a note">
        <div className="space-y-2">
          <Select value={newKind} onChange={(e) => setNewKind(e.target.value as PersonNoteKind)} className="!w-36">
            {NOTE_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
          <Textarea
            rows={2}
            placeholder="What happened? (Ctrl+Enter to add)"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault()
                submitNew()
              }
            }}
          />
          <div className="flex justify-end">
            <Button size="sm" disabled={!newNote.trim() || add.isPending} onClick={submitNew}>
              <Plus size={13} /> Add note
            </Button>
          </div>
        </div>
      </Section>

      <Section title="Timeline">
        <div className="mb-3 flex flex-wrap gap-1.5">
          <button
            onClick={() => setKindFilter('')}
            className={cn(
              'rounded-full px-2.5 py-1 text-[11px] font-medium capitalize transition-colors',
              kindFilter === ''
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700',
            )}
          >
            All
          </button>
          {NOTE_KINDS.map((k) => (
            <button
              key={k}
              onClick={() => setKindFilter(k)}
              className={cn(
                'rounded-full px-2.5 py-1 text-[11px] font-medium capitalize transition-colors',
                kindFilter === k
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700',
              )}
            >
              {k}
            </button>
          ))}
        </div>

        {isLoading ? (
          <Spinner />
        ) : notes.length === 0 ? (
          <p className="text-xs text-slate-400">
            No notes yet. Log feedback, calls and observations here to build a picture over time.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {notes.map((note) => (
              <li key={note.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
                {editingId === note.id ? (
                  <div className="space-y-2">
                    <Select value={editKind} onChange={(e) => setEditKind(e.target.value as PersonNoteKind)} className="!w-36">
                      {NOTE_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </Select>
                    <Textarea rows={2} value={editText} onChange={(e) => setEditText(e.target.value)} />
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                        Cancel
                      </Button>
                      <Button size="sm" disabled={!editText.trim() || update.isPending} onClick={() => saveEdit(note.id)}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <Badge tone={noteKindTone[note.kind]} className="mr-1.5 capitalize">
                          {note.kind}
                        </Badge>
                        <span className="font-medium">{fmtDate(note.noted_on)}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <button
                          onClick={() => toggleDiscussed(note)}
                          className={cn(
                            'flex items-center gap-0.5 text-[10px] font-medium',
                            note.discussed_on ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300',
                          )}
                          title={note.discussed_on ? `Discussed ${fmtDate(note.discussed_on)} — click to unmark` : 'Mark as discussed'}
                        >
                          <Check size={11} /> {note.discussed_on ? 'discussed' : 'undiscussed'}
                        </button>
                        <button onClick={() => startEdit(note)} className="text-slate-400 hover:text-indigo-500">
                          <Pencil size={13} />
                        </button>
                        <button onClick={() => remove.mutate(note.id)} className="text-slate-400 hover:text-rose-500">
                          <Trash2 size={13} />
                        </button>
                      </span>
                    </div>
                    <p className="mt-1.5 whitespace-pre-wrap text-slate-700 dark:text-slate-200">{note.note}</p>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Drawer>
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
    pin_discussion: person?.pin_discussion ? 'true' : 'false',
  })
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: form.name,
        email: form.email || null,
        team: form.team || null,
        role: form.role || null,
        is_bpm: form.is_bpm === 'true',
      }
      // only meaningful on an existing person — pinning is enforced exclusive
      // by the PATCH endpoint, which a fresh person never goes through here
      if (person) body.pin_discussion = form.pin_discussion === 'true'
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
          {person && (
            <Field label="Pin their list to Today">
              <Select value={form.pin_discussion} onChange={set('pin_discussion')}>
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>
            </Field>
          )}
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
  const [editing, setEditing] = useState<number | null>(null)
  const { data: workstreams, isLoading } = useQuery({
    queryKey: ['workstreams', 'all'],
    queryFn: () => api.get<Workstream[]>('/workstreams?include_closed=true'),
  })
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.patch(`/workstreams/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workstreams'] }),
  })
  // The server renumbers to 1..N and returns the new order, so the response is
  // the source of truth rather than the optimistic arrayMove.
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.post('/workstreams/reorder', { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workstreams'] }),
    onError: (e: Error) => toast.error(e.message),
  })

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id || !workstreams) return
    const ids = workstreams.map((ws) => ws.id)
    reorder.mutate(arrayMove(ids, ids.indexOf(Number(active.id)), ids.indexOf(Number(over.id))))
  }

  if (isLoading) return <Spinner />
  if (!workstreams?.length)
    return <EmptyState title="No workstreams" hint="Audits, investigations, initiatives, governance cycles — the lanes your work runs in." />

  return (
    <>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Drag to set the order — it drives the rolling agenda bands, the planner lanes and every workstream dropdown.
      </p>
      <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={workstreams.map((ws) => ws.id)} strategy={rectSortingStrategy}>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {workstreams.map((ws) => (
              <SortableWorkstreamCard
                key={ws.id}
                ws={ws}
                selected={selection.selected.has(ws.id)}
                onToggle={() => selection.toggle(ws.id)}
                onEdit={() => setEditing(ws.id)}
                onStatus={(status) => patch.mutate({ id: ws.id, body: { status } })}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      <BulkBar type="workstream" ids={[...selection.selected]} onClear={selection.clear} />
      {editing && <WorkstreamDrawer key={editing} id={editing} onClose={() => setEditing(null)} />}
    </>
  )
}

function SortableWorkstreamCard({
  ws,
  selected,
  onToggle,
  onEdit,
  onStatus,
}: {
  ws: Workstream
  selected: boolean
  onToggle: () => void
  onEdit: () => void
  onStatus: (status: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: ws.id })

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'rounded-xl border bg-white p-4 shadow-sm dark:bg-slate-900',
        isDragging && 'z-10 opacity-80 shadow-md',
        selected ? 'border-indigo-400 dark:border-indigo-600' : 'border-slate-200 dark:border-slate-800',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-[13px] font-semibold">
          <button
            {...attributes}
            {...listeners}
            aria-label={`Reorder ${ws.name}`}
            className="cursor-grab text-slate-300 hover:text-slate-500 active:cursor-grabbing dark:text-slate-600"
          >
            <GripVertical size={14} />
          </button>
          <SelectCheckbox checked={selected} onChange={onToggle} label={`Select ${ws.name}`} />
          <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: ws.colour }} />
          <span className="truncate">{ws.name}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          <span title="Display order">
            <Badge tone="slate">#{ws.sort_order}</Badge>
          </span>
          <Badge tone={ws.status === 'active' ? 'green' : 'slate'}>{ws.status}</Badge>
        </span>
      </div>
      <div className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
        {ws.category} · {peopleLabel(ws.owners) || 'no owner'}
      </div>
      <div className="mt-3 flex gap-1.5">
        <Button size="sm" variant="secondary" onClick={onEdit}>
          <Pencil size={13} /> Edit
        </Button>
        {ws.status === 'active' ? (
          <Button size="sm" variant="secondary" onClick={() => onStatus('closed')}>
            Close
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => onStatus('active')}>
            Reopen
          </Button>
        )}
      </div>
    </div>
  )
}

function WorkstreamDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: workstreams = [] } = useQuery({
    queryKey: ['workstreams', 'all'],
    queryFn: () => api.get<Workstream[]>('/workstreams?include_closed=true'),
  })
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const item = workstreams.find((ws) => ws.id === id)

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/workstreams/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workstreams'] }),
    onError: (e: Error) => toast.error(e.message),
  })

  if (!item) return null
  return (
    <Drawer open onClose={onClose} title={item.name}>
      <Field label="Name">
        <Input
          defaultValue={item.name}
          onBlur={(e) => {
            const name = e.target.value.trim()
            if (!name) {
              e.target.value = item.name // an unnamed workstream is unpickable in every dropdown
              return
            }
            if (name !== item.name) patch.mutate({ name })
          }}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Category">
          <Select value={item.category} onChange={(e) => patch.mutate({ category: e.target.value })}>
            <option value="audit">audit</option>
            <option value="investigation">investigation</option>
            <option value="initiative">initiative</option>
            <option value="governance">governance</option>
          </Select>
        </Field>
        <Field label="Status">
          <Select value={item.status} onChange={(e) => patch.mutate({ status: e.target.value })}>
            <option value="active">active</option>
            <option value="paused">paused</option>
            <option value="closed">closed</option>
          </Select>
        </Field>
        <Field label="Colour">
          <Input
            type="color"
            defaultValue={item.colour}
            onBlur={(e) => e.target.value !== item.colour && patch.mutate({ colour: e.target.value })}
            className="!h-9 !p-1"
          />
        </Field>
        <Field label="Order">
          <Input
            type="number"
            min={1}
            defaultValue={item.sort_order}
            onBlur={(e) => {
              const sort_order = Number(e.target.value)
              if (sort_order && sort_order !== item.sort_order) patch.mutate({ sort_order })
            }}
            title="Same number the drag handles set — lower sorts first"
          />
        </Field>
      </div>
      <Field label="Owners">
        <MultiSelect
          value={item.owners.map((o) => o.id)}
          onChange={(owner_ids) => patch.mutate({ owner_ids })}
          options={people}
          emptyLabel="No owner"
        />
      </Field>
      <Field label="Description">
        <Textarea
          rows={3}
          defaultValue={item.description ?? ''}
          onBlur={(e) => e.target.value !== (item.description ?? '') && patch.mutate({ description: e.target.value || null })}
        />
      </Field>
    </Drawer>
  )
}

function WorkstreamModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const [form, setForm] = useState<Record<string, string>>({ colour: '#6366f1', category: 'initiative' })
  const [ownerIds, setOwnerIds] = useState<number[]>([])
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const create = useMutation({
    mutationFn: () =>
      // sort_order omitted on purpose — the server appends, so a new workstream
      // does not land at the top of everyone's rolling agenda
      api.post('/workstreams', {
        name: form.name,
        category: form.category,
        colour: form.colour,
        owner_ids: ownerIds,
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
          <Field label="Colour">
            <Input type="color" value={form.colour} onChange={set('colour')} className="!h-9 !p-1" />
          </Field>
        </div>
        <Field label="Owners">
          <MultiSelect value={ownerIds} onChange={setOwnerIds} options={people} emptyLabel="No owner" />
        </Field>
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
