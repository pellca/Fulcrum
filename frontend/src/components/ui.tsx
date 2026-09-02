import { type ReactNode, useEffect } from 'react'
import { clsx } from 'clsx'
import { X } from 'lucide-react'

export function cn(...args: Parameters<typeof clsx>) {
  return clsx(...args)
}

// ---------- Button ----------

const buttonVariants = {
  primary:
    'bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-indigo-400 shadow-sm',
  secondary:
    'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800',
  ghost:
    'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
  danger: 'bg-rose-600 text-white hover:bg-rose-500 shadow-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof buttonVariants
  size?: 'sm' | 'md'
}) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60',
        size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm',
        buttonVariants[variant],
        className,
      )}
      {...props}
    />
  )
}

// ---------- Card ----------

export function Card({
  title,
  actions,
  children,
  className,
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
    >
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}

// ---------- Badge ----------

const badgeTones: Record<string, string> = {
  slate: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  red: 'bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-300',
  blue: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  indigo: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  violet: 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-300',
}

export function Badge({ tone = 'slate', children, className }: { tone?: string; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
        badgeTones[tone] ?? badgeTones.slate,
        className,
      )}
    >
      {children}
    </span>
  )
}

export const statusTone: Record<string, string> = {
  todo: 'slate',
  in_progress: 'blue',
  blocked: 'red',
  done: 'green',
  cancelled: 'slate',
  open: 'slate',
  on_track: 'green',
  at_risk: 'red',
  delivered: 'green',
  dropped: 'slate',
  planned: 'slate',
  agenda_set: 'blue',
  held: 'green',
  proposed: 'slate',
  scheduled: 'blue',
  discussed: 'green',
  parked: 'amber',
  decided: 'green',
  pending: 'amber',
  revisit: 'violet',
  running: 'blue',
  succeeded: 'green',
  failed: 'red',
}

export const priorityTone: Record<string, string> = { high: 'red', medium: 'amber', low: 'slate' }

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone[status] ?? 'slate'}>{status.replace('_', ' ')}</Badge>
}

export const intentTone: Record<string, string> = { decide: 'indigo', inform: 'blue', consult: 'violet', shape: 'amber' }

export function IntentBadge({ intent }: { intent: string }) {
  return <Badge tone={intentTone[intent] ?? 'slate'}>{intent}</Badge>
}

// Solid fills for grid cells — e.g. a matrix where intent is the cell background.
export const intentSolid: Record<string, string> = {
  decide: 'bg-indigo-500 text-white',
  inform: 'bg-sky-500 text-white',
  consult: 'bg-violet-500 text-white',
  shape: 'bg-amber-500 text-white',
  slate: 'bg-slate-400 text-white',
}

/** Name list for a many-to-many people field. Somewhere like a rolling-agenda
 *  card there is room for one name, so past `max` it becomes "Priya Shah +2"
 *  rather than wrapping to three lines or truncating mid-name. */
export function peopleLabel(
  people: { name: string }[] | null | undefined,
  max = Infinity,
): string {
  if (!people?.length) return ''
  if (people.length <= max) return people.map((p) => p.name).join(', ')
  return `${people.slice(0, max).map((p) => p.name).join(', ')} +${people.length - max}`
}

export function allocatedMinutes(items: { allocated_minutes: number }[]): number {
  return items.reduce((sum, item) => sum + item.allocated_minutes, 0)
}

/** Running clock times for an agenda, in sequence order, from the meeting's
 *  `scheduled_at`. Pure and client-side: nothing here is persisted, so a
 *  builder can retime live as items are dragged or their minutes edited,
 *  and it can never fall out of step with `sequence`. An agenda that
 *  overruns its capacity just runs past the end time — the capacity bar
 *  is what flags the overrun, not this helper. */
export function agendaTimes(
  startISO: string,
  items: { allocated_minutes: number }[],
): { start: string; end: string }[] {
  const fmt = (d: Date) => d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  let cursor = new Date(startISO)
  return items.map((item) => {
    const start = cursor
    cursor = new Date(cursor.getTime() + item.allocated_minutes * 60000)
    return { start: fmt(start), end: fmt(cursor) }
  })
}

export function CapacityBar({
  allocated,
  capacity,
  size = 'md',
  className,
}: {
  allocated: number
  capacity: number
  size?: 'sm' | 'md'
  className?: string
}) {
  const over = allocated > capacity
  const noCapacity = capacity <= 0
  const pct = noCapacity ? (allocated > 0 ? 100 : 0) : Math.min(100, (allocated / capacity) * 100)
  return (
    <div
      className={cn(
        'overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800',
        size === 'sm' ? 'h-1.5' : 'h-2',
        className,
      )}
    >
      <div
        className={cn('h-full rounded-full transition-all', over || (noCapacity && allocated > 0) ? 'bg-rose-500' : 'bg-indigo-500')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ---------- form fields ----------

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
        props.className,
      )}
    />
  )
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
        props.className,
      )}
    />
  )
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
        props.className,
      )}
    />
  )
}

/** Two-or-more mutually exclusive views, for when a dropdown would hide the
 *  fact that there is a choice at all. */
export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string; title?: string }[]
  className?: string
}) {
  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex rounded-lg border border-slate-300 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800',
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          type="button"
          aria-selected={option.value === value}
          title={option.title}
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            option.value === value
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-slate-100'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** Pick several from a list — chips for what is chosen, a select of what is left.
 *  A plain <select multiple> is unreadable past a handful of options and gives no
 *  hint that ctrl-click is required, which is why this exists instead. */
export function MultiSelect({
  value,
  onChange,
  options,
  placeholder = 'Add…',
  emptyLabel = 'None',
}: {
  value: number[]
  onChange: (value: number[]) => void
  options: { id: number; name: string }[]
  placeholder?: string
  emptyLabel?: string
}) {
  const chosen = value
    .map((id) => options.find((option) => option.id === id))
    .filter((option): option is { id: number; name: string } => Boolean(option))
  const remaining = options.filter((option) => !value.includes(option.id))

  return (
    <div className="rounded-lg border border-slate-300 bg-white p-1.5 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-1">
        {chosen.length === 0 ? (
          <span className="px-1 text-xs text-slate-400">{emptyLabel}</span>
        ) : (
          chosen.map((option) => (
            <span
              key={option.id}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-0.5 pr-1 pl-2 text-[11px] font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              {option.name}
              <button
                type="button"
                aria-label={`Remove ${option.name}`}
                onClick={() => onChange(value.filter((id) => id !== option.id))}
                className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-100"
              >
                <X size={11} />
              </button>
            </span>
          ))
        )}
      </div>
      {remaining.length > 0 && (
        <select
          value=""
          onChange={(e) => e.target.value && onChange([...value, Number(e.target.value)])}
          className="mt-1 w-full rounded-md border-0 bg-transparent px-1 py-1 text-xs text-slate-500 focus:outline-none dark:text-slate-400"
        >
          <option value="">{placeholder}</option>
          {remaining.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
      {children}
    </label>
  )
}

// ---------- Modal ----------

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/40 p-4 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div
        className={cn(
          'w-full rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900',
          wide ? 'max-w-3xl' : 'max-w-lg',
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800">
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

// ---------- misc ----------

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      {icon && <div className="text-slate-300 dark:text-slate-600">{icon}</div>}
      <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-400 dark:text-slate-500">{hint}</p>}
    </div>
  )
}

export function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function fmtDate(iso: string | null | undefined, opts?: Intl.DateTimeFormatOptions) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', opts ?? { day: 'numeric', month: 'short' })
}

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}, ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
}

export function dueTone(due: string | null | undefined, doneish = false): string {
  if (!due || doneish) return 'slate'
  const days = Math.floor((new Date(due).getTime() - Date.now()) / 86400000)
  if (days < 0) return 'red'
  if (days <= 3) return 'amber'
  return 'slate'
}
