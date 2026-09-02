import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Link2, Trash2, X } from 'lucide-react'
import { api, type Chase, type LinkItem } from '../api'
import { Badge, Button, cn, Field, fmtDate, Input, Select } from './ui'
import { entityRoute } from './entityRoutes'

// ---------- side drawer ----------

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/30 backdrop-blur-[2px]" onMouseDown={onClose}>
      <div
        className="h-full w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/95 px-5 py-3.5 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
          <h2 className="pr-4 text-sm font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-5 p-5">{children}</div>
      </div>
    </div>
  )
}

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-slate-400">{title}</h3>
        {actions}
      </div>
      {children}
    </section>
  )
}

// ---------- chases ----------

export function ChasePanel({ kind, itemId }: { kind: 'action' | 'commitment'; itemId: number }) {
  const queryClient = useQueryClient()
  const key = kind === 'action' ? 'action_id' : 'commitment_id'
  const { data: chases = [] } = useQuery({
    queryKey: ['chases', kind, itemId],
    queryFn: () => api.get<Chase[]>(`/chases?${key}=${itemId}`),
  })
  const [note, setNote] = useState('')
  const [method, setMethod] = useState('email')
  const [nextDays, setNextDays] = useState('7')

  const add = useMutation({
    mutationFn: () =>
      api.post('/chases', {
        [key]: itemId,
        chased_on: new Date().toISOString().slice(0, 10),
        method,
        note: note || null,
        next_chase_on: nextDays
          ? new Date(Date.now() + Number(nextDays) * 86400000).toISOString().slice(0, 10)
          : null,
      }),
    onSuccess: () => {
      toast.success('Chase logged')
      setNote('')
      queryClient.invalidateQueries({ queryKey: ['chases', kind, itemId] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  return (
    <Section title="Chase history">
      <div className="mb-3 flex items-end gap-2">
        <div className="flex-1">
          <Input placeholder="What did you chase / agree?" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <Select value={method} onChange={(e) => setMethod(e.target.value)} className="!w-28">
          <option value="email">Email</option>
          <option value="chat">Chat</option>
          <option value="meeting">Meeting</option>
        </Select>
        <Select value={nextDays} onChange={(e) => setNextDays(e.target.value)} className="!w-32" title="Re-chase in">
          <option value="">No re-chase</option>
          <option value="2">Again in 2d</option>
          <option value="7">Again in 7d</option>
          <option value="14">Again in 14d</option>
        </Select>
        <Button size="sm" onClick={() => add.mutate()}>
          Log
        </Button>
      </div>
      {chases.length === 0 ? (
        <p className="text-xs text-slate-400">No chases logged yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {chases.map((chase) => (
            <li key={chase.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
              <span className="font-medium">{fmtDate(chase.chased_on)}</span>
              <span className="text-slate-500"> via {chase.method}</span>
              {chase.note && <span> — {chase.note}</span>}
              {chase.next_chase_on && (
                <Badge tone="blue" className="ml-2">
                  re-chase {fmtDate(chase.next_chase_on)}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

// ---------- links ----------

const LINKABLE: { value: string; label: string; endpoint: string; titleKey: string }[] = [
  { value: 'action', label: 'Action', endpoint: '/actions?open_only=true', titleKey: 'title' },
  { value: 'commitment', label: 'Commitment', endpoint: '/commitments?open_only=true', titleKey: 'title' },
  { value: 'topic', label: 'Topic', endpoint: '/topics', titleKey: 'title' },
  { value: 'key_date', label: 'Key date', endpoint: '/key-dates', titleKey: 'title' },
  { value: 'workstream', label: 'Workstream', endpoint: '/workstreams', titleKey: 'name' },
  { value: 'discussion_point', label: 'Discussion point', endpoint: '/discussion-points', titleKey: 'title' },
  { value: 'person', label: 'Person', endpoint: '/people', titleKey: 'name' },
]

const KIND_LABEL: Record<string, string> = {
  blocks: 'blocks',
  precedes: 'must precede',
  informs: 'informs',
  relates: 'relates to',
}

export function LinkPanel({ entityType, entityId }: { entityType: string; entityId: number }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: links = [] } = useQuery({
    queryKey: ['links', entityType, entityId],
    queryFn: () => api.get<LinkItem[]>(`/links/for/${entityType}/${entityId}`),
  })
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState('relates')
  const [direction, setDirection] = useState<'out' | 'in'>('out')
  const [targetType, setTargetType] = useState('action')
  const [targetId, setTargetId] = useState('')

  const targetMeta = LINKABLE.find((l) => l.value === targetType)!
  const { data: targets = [] } = useQuery({
    queryKey: ['link-targets', targetType],
    queryFn: () => api.get<Record<string, unknown>[]>(targetMeta.endpoint),
    enabled: adding,
  })

  const add = useMutation({
    mutationFn: () => {
      const self = { type: entityType, id: entityId }
      const other = { type: targetType, id: Number(targetId) }
      const [from, to] = direction === 'out' ? [self, other] : [other, self]
      return api.post('/links', {
        from_type: from.type,
        from_id: from.id,
        to_type: to.type,
        to_id: to.id,
        kind,
      })
    },
    onSuccess: () => {
      setAdding(false)
      setTargetId('')
      queryClient.invalidateQueries({ queryKey: ['links', entityType, entityId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/links/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['links', entityType, entityId] }),
  })

  return (
    <Section
      title="Links & dependencies"
      actions={
        <Button size="sm" variant="ghost" onClick={() => setAdding((a) => !a)}>
          <Link2 size={13} /> {adding ? 'Cancel' : 'Add link'}
        </Button>
      }
    >
      {adding && (
        <div className="mb-3 space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3 dark:border-indigo-900 dark:bg-indigo-950/30">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Relationship">
              <Select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="blocks">blocks (dependency)</option>
                <option value="precedes">precedes (sequence)</option>
                <option value="informs">informs</option>
                <option value="relates">relates to</option>
              </Select>
            </Field>
            <Field label="Direction">
              <Select value={direction} onChange={(e) => setDirection(e.target.value as 'out' | 'in')}>
                <option value="out">this item → other</option>
                <option value="in">other → this item</option>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Target type">
              <Select
                value={targetType}
                onChange={(e) => {
                  setTargetType(e.target.value)
                  setTargetId('')
                }}
              >
                {LINKABLE.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Target">
              <Select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                <option value="">Choose…</option>
                {targets
                  .filter((t) => !(targetType === entityType && t.id === entityId))
                  .map((t) => (
                    <option key={String(t.id)} value={String(t.id)}>
                      {String(t[targetMeta.titleKey])}
                    </option>
                  ))}
              </Select>
            </Field>
          </div>
          <Button size="sm" disabled={!targetId} onClick={() => add.mutate()}>
            Create link
          </Button>
        </div>
      )}
      {links.length === 0 ? (
        <p className="text-xs text-slate-400">
          No links yet. Use <em>blocks</em>/<em>precedes</em> to build dependency chains the planner can track.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {links.map((link) => {
            const outgoing = link.from_type === entityType && link.from_id === entityId
            const otherType = outgoing ? link.to_type : link.from_type
            const otherId = outgoing ? link.to_id : link.from_id
            const otherTitle = outgoing ? link.to_title : link.from_title
            const route = entityRoute(otherType, otherId)
            return (
              <li key={link.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
                <span className="min-w-0">
                  <Badge tone={link.kind === 'blocks' ? 'red' : link.kind === 'precedes' ? 'amber' : 'slate'} className="mr-1.5">
                    {outgoing ? KIND_LABEL[link.kind] : `is ${link.kind === 'blocks' ? 'blocked by' : link.kind === 'precedes' ? 'preceded by' : KIND_LABEL[link.kind]}`}
                  </Badge>
                  {route ? (
                    <button
                      onClick={() => navigate(route)}
                      className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      {otherTitle}
                    </button>
                  ) : (
                    <span className={cn('font-medium', !outgoing && 'text-slate-600 dark:text-slate-300')}>{otherTitle}</span>
                  )}
                  <span className="ml-1 text-slate-400">({otherType})</span>
                </span>
                <button onClick={() => remove.mutate(link.id)} className="shrink-0 text-slate-400 hover:text-rose-500">
                  <Trash2 size={13} />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Section>
  )
}
