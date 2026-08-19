import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  CheckCircle2,
  EyeOff,
  FolderOpen,
  Paperclip,
  PhoneCall,
  Plus,
  Reply,
  RotateCcw,
  StickyNote,
  Upload,
  UserRound,
  X,
} from 'lucide-react'
import {
  api,
  getMailMessage,
  importMailPath,
  importMailUpload,
  listMailMessages,
  mailCloseAction,
  mailCreateAction,
  mailDismiss,
  mailLogChase,
  mailPersonNote,
  mailReopen,
  mailStats,
  mailSuggestions,
  registerPicker,
  type MailFolder,
  type MailMessage,
  type MailRecipient,
  type MailSuggestion,
  type MailSuggestionType,
  type MailTriage,
  type Person,
  type PersonMini,
  type PersonNoteKind,
  type RegisterPickerItem,
} from '../api'
import { Badge, Button, cn, EmptyState, Field, fmtDate, fmtDateTime, Input, PageHeader, Select, Spinner, statusTone, Textarea } from '../components/ui'
import { Section } from '../components/panels'

type FolderFilter = 'all' | MailFolder
type TriageFilter = 'all' | MailTriage
type ActiveForm = 'chase' | 'action' | 'close' | 'note' | null

const DAY_OPTIONS = [1, 2, 3, 4, 5] as const
const FOLDER_OPTIONS: { value: FolderFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'inbox', label: 'Inbox' },
  { value: 'sent', label: 'Sent' },
]
const TRIAGE_OPTIONS: { value: TriageFilter; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'linked', label: 'Linked' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'all', label: 'All' },
]

const triageTone: Record<MailTriage, string> = { pending: 'amber', linked: 'green', dismissed: 'slate' }

function formatTime(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

function messageTimestamp(m: MailMessage) {
  return m.folder === 'sent' ? (m.sent_at ?? m.received_at) : (m.received_at ?? m.sent_at)
}

function recipientLabel(recipients: MailRecipient[]) {
  if (recipients.length === 0) return '(no recipients)'
  const first = recipients[0].name || recipients[0].email || '(unknown)'
  return recipients.length > 1 ? `${first} +${recipients.length - 1}` : first
}

function firstToken(name: string) {
  return name.trim().split(/\s+/)[0] ?? ''
}

function mentionToken(name: string) {
  return name.includes(' ') ? `@"${name}"` : `@${name}`
}

// inbox mail: prefer the resolved sender's full name; fall back to the raw
// sender's first name so an unmatched "Sarah Chen (external)" doesn't quote-break the grammar
function inboxMentionName(message: MailMessage): string {
  if (message.sender_person) return message.sender_person.name
  return firstToken(message.sender_name || message.sender_email || '')
}

// sent mail: prefer the first recipient that resolved to a known person
function sentMentionName(message: MailMessage): string {
  for (const r of message.to_recipients) {
    const match = message.matched_people.find((p) => r.email && p.matched_email === r.email.toLowerCase())
    if (match) return match.name
  }
  const first = message.to_recipients[0]
  return first ? firstToken(first.name || first.email || '') : ''
}

function quickAddPrefill(message: MailMessage): string {
  const rawSubject = message.subject || '(no subject)'
  // strip quick-add grammar tokens (@, #, !) out of the subject so a real
  // subject like "#INC0012345" doesn't get parsed as a workstream token
  const subject = rawSubject.replace(/[@#!]/g, ' ').replace(/\s+/g, ' ').trim()
  const name = message.folder === 'sent' ? sentMentionName(message) : inboxMentionName(message)
  return name ? `${subject} ${mentionToken(name)} due:+7` : `${subject} due:+7`
}

function mailtoHref(message: MailMessage): string | null {
  if (message.folder !== 'inbox' || !message.sender_email) return null
  return `mailto:${message.sender_email}?subject=RE:%20${encodeURIComponent(message.subject || '')}`
}

function PersonChip({ name }: { name: string }) {
  return (
    <Badge tone="indigo" className="gap-1">
      <UserRound size={10} /> {name}
    </Badge>
  )
}

function Segmented<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900">
      {options.map((opt) => (
        <button
          key={String(opt.value)}
          onClick={() => onChange(opt.value)}
          className={cn(
            'rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors',
            value === opt.value
              ? 'bg-indigo-600 text-white'
              : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export default function Mailbox() {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [days, setDays] = useState<number>(5)
  const [folder, setFolder] = useState<FolderFilter>('all')
  const [triage, setTriage] = useState<TriageFilter>('pending')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [importPath, setImportPath] = useState('')
  const [activeForm, setActiveForm] = useState<ActiveForm>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    setActiveForm(null)
  }, [selectedId])

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['mail', days, folder, triage],
    queryFn: () =>
      listMailMessages({
        days,
        folder: folder === 'all' ? undefined : folder,
        triage: triage === 'all' ? undefined : triage,
      }),
  })

  const { data: stats } = useQuery({ queryKey: ['mail-stats'], queryFn: mailStats })

  const invalidateMail = () => {
    queryClient.invalidateQueries({ queryKey: ['mail'] })
    queryClient.invalidateQueries({ queryKey: ['mail-stats'] })
  }

  // after any triage-rail verb: mail list/stats/suggestions plus everything
  // else (register, people, dashboard) that might now reference a new/updated
  // action, commitment or note
  const invalidateAfterVerb = (id: number) => {
    invalidateMail()
    queryClient.invalidateQueries({ queryKey: ['mail-suggestions', id] })
    queryClient.invalidateQueries()
  }

  // inbox-zero flow: after dismissing the selected message, move on to the
  // next one in the currently loaded (filtered) list rather than stranding
  // the reader on a message that just left the triage queue
  const advanceSelection = (dismissedId: number) => {
    if (selectedId !== dismissedId) return
    const idx = messages.findIndex((m) => m.id === dismissedId)
    const remaining = messages.filter((m) => m.id !== dismissedId)
    const nextId = idx === -1 || remaining.length === 0 ? null : remaining[Math.min(idx, remaining.length - 1)].id
    if (dismissedId === linkedId) {
      // dismissing the deep-linked message would otherwise leave ?msg=
      // pointing at a message that's no longer selected — route through
      // selectMessage so it drops the param the same as any other pick
      selectMessage(nextId)
    } else {
      setSelectedId(nextId)
    }
  }

  const dismissMutation = useMutation({
    mutationFn: (id: number) => mailDismiss(id),
    onSuccess: (_res, id) => {
      invalidateAfterVerb(id)
      toast.success('Dismissed')
      advanceSelection(id)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const reopenMutation = useMutation({
    mutationFn: (id: number) => mailReopen(id),
    onSuccess: (_res, id) => {
      invalidateAfterVerb(id)
      toast.success('Reopened')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const importSuccess = (summary: { added: number; updated: number; purged: number; duplicates?: number }) => {
    const notes = [
      summary.duplicates ? `${summary.duplicates} duplicate id(s) collapsed.` : null,
      summary.purged ? `${summary.purged} message(s) purged past retention.` : null,
    ].filter(Boolean)
    toast.success(`Mail imported: ${summary.added} added, ${summary.updated} updated`, {
      description: notes.length ? notes.join(' ') : undefined,
    })
    invalidateMail()
  }

  const importFromPath = useMutation({
    mutationFn: () => importMailPath(importPath.trim()),
    onSuccess: (summary) => {
      importSuccess(summary)
      setImportPath('')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const importFromUpload = useMutation({
    mutationFn: (file: File) => importMailUpload(file),
    onSuccess: importSuccess,
    onError: (e: Error) => toast.error(e.message),
  })

  // thread counts within the currently loaded set
  const threadCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const m of messages) {
      if (!m.conversation_id) continue
      counts.set(m.conversation_id, (counts.get(m.conversation_id) ?? 0) + 1)
    }
    return counts
  }, [messages])

  // deep link: ?msg=<id> selects (and, if necessary, fetches) a message even
  // when it falls outside the current day/folder/triage filters
  const linkedId = (() => {
    const raw = searchParams.get('msg')
    const n = raw ? Number(raw) : NaN
    return Number.isFinite(n) ? n : null
  })()

  const { data: linkedMessage, isError: linkedMessageErrored } = useQuery({
    queryKey: ['mail-message', linkedId],
    queryFn: () => getMailMessage(linkedId!),
    enabled: linkedId != null,
    retry: false,
  })

  useEffect(() => {
    if (linkedId != null) setSelectedId(linkedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkedId])

  // choosing a different message (click or keyboard) drops the ?msg= deep
  // link — it only tracks the message that was linked to, not the selection
  const selectMessage = useCallback(
    (id: number | null) => {
      setSelectedId(id)
      setSearchParams((prev) => {
        if (!prev.has('msg')) return prev
        const next = new URLSearchParams(prev)
        next.delete('msg')
        return next
      }, { replace: true })
    },
    [setSearchParams],
  )

  const clearLinkedMessage = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('msg')
    setSearchParams(next, { replace: true })
    setSelectedId(null)
  }

  const selected =
    messages.find((m) => m.id === selectedId) ?? (linkedMessage && linkedMessage.id === selectedId ? linkedMessage : null)
  const selectedOutsideFilters = selected != null && !messages.some((m) => m.id === selected.id)
  // deep link pointed at a message that's gone (purged past retention, most
  // likely) — the fetch for it 404s, so there's nothing to select
  const linkedMessageMissing = linkedId != null && selectedId === linkedId && linkedMessageErrored && selected == null

  // j/k or arrow up/down moves selection; c/a/x/n/e/z drive the action rail
  // verbs for the selected message — all ignored while a form field has focus
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const tag = (document.activeElement?.tagName ?? '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      // a focused suggestion/picker row (HoverDetailTarget) is also a
      // "form field" for this purpose — j/k etc shouldn't hijack it while
      // it's focused for its own Escape-to-close handling
      if (document.activeElement?.closest('[data-hover-target]')) return

      if (e.key === 'j' || e.key === 'k' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (messages.length === 0) return
        e.preventDefault()
        const down = e.key === 'j' || e.key === 'ArrowDown'
        const currentIndex = messages.findIndex((m) => m.id === selectedId)
        const nextIndex =
          currentIndex === -1 ? 0 : down ? Math.min(currentIndex + 1, messages.length - 1) : Math.max(currentIndex - 1, 0)
        selectMessage(messages[nextIndex].id)
        return
      }

      if (selectedId == null) return
      const current = messages.find((m) => m.id === selectedId)
      if (!current) return

      switch (e.key.toLowerCase()) {
        case 'c':
          e.preventDefault()
          setActiveForm('chase')
          break
        case 'a':
          e.preventDefault()
          setActiveForm('action')
          break
        case 'x':
          e.preventDefault()
          setActiveForm('close')
          break
        case 'n':
          e.preventDefault()
          setActiveForm('note')
          break
        case 'e':
          if (activeForm === null && current.triage === 'pending') {
            e.preventDefault()
            dismissMutation.mutate(selectedId)
          }
          break
        case 'z':
          if (activeForm === null && current.triage !== 'pending') {
            e.preventDefault()
            reopenMutation.mutate(selectedId)
          }
          break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [messages, selectedId, dismissMutation, reopenMutation, activeForm, selectMessage])

  return (
    <div>
      <PageHeader
        title="Mailbox"
        subtitle="Triage recent mail — see what's landed before you decide what it means"
        actions={
          <>
            <Input
              value={importPath}
              onChange={(e) => setImportPath(e.target.value)}
              placeholder="/path/to/mailbox.json"
              className="!w-56"
            />
            <Button
              variant="secondary"
              disabled={!importPath.trim() || importFromPath.isPending}
              onClick={() => importFromPath.mutate()}
            >
              <FolderOpen size={15} /> Import path
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) importFromUpload.mutate(file)
                e.target.value = ''
              }}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={importFromUpload.isPending}>
              <Upload size={15} /> {importFromUpload.isPending ? 'Importing…' : 'Upload mailbox.json'}
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented options={DAY_OPTIONS.map((d) => ({ value: d, label: String(d) }))} value={days} onChange={setDays} />
        <Segmented options={FOLDER_OPTIONS} value={folder} onChange={setFolder} />
        <Segmented options={TRIAGE_OPTIONS} value={triage} onChange={setTriage} />
        {stats && (
          <span className="ml-auto text-xs text-slate-400">
            {stats.pending} pending of {stats.total}
          </span>
        )}
      </div>

      {isLoading ? (
        <Spinner />
      ) : stats?.total === 0 ? (
        <EmptyState
          title="No mail imported yet"
          hint="Run the mail extractor (tools/mail_extractor) against your Outlook mailbox to produce a mailbox.json, then import it above — inbox and sent mail from the last 5 days will land here for triage."
        />
      ) : messages.length === 0 && !selected && !linkedMessageMissing ? (
        <EmptyState title="No messages match these filters" hint="Try widening the day range, folder or triage filter." />
      ) : (
        <div className="flex gap-4">
          <div className="h-[70vh] w-96 shrink-0 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            {messages.map((m) => (
              <MessageRow
                key={m.id}
                message={m}
                selected={m.id === selectedId}
                threadCount={m.conversation_id ? (threadCounts.get(m.conversation_id) ?? 0) : 0}
                onClick={() => selectMessage(m.id)}
              />
            ))}
          </div>
          <div className="h-[70vh] min-w-0 flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            {selected ? (
              <>
                {selectedOutsideFilters && (
                  <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                    <span>Linked message — outside current filters</span>
                    <button
                      onClick={clearLinkedMessage}
                      className="shrink-0 rounded p-0.5 text-amber-600 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200"
                      aria-label="Clear linked message"
                    >
                      <X size={13} />
                    </button>
                  </div>
                )}
                <ReadingPane message={selected} />
              </>
            ) : linkedMessageMissing ? (
              <div className="flex items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                <span>Linked message is no longer available — it may have passed the retention window</span>
                <button
                  onClick={clearLinkedMessage}
                  className="shrink-0 rounded p-0.5 text-amber-600 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200"
                  aria-label="Clear linked message"
                >
                  <X size={13} />
                </button>
              </div>
            ) : (
              <EmptyState title="Select a message" hint="Pick something from the list on the left — j/k or the arrow keys move the selection." />
            )}
          </div>
          <div className="h-[70vh] w-80 shrink-0 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            {selected ? (
              <ActionRail
                message={selected}
                activeForm={activeForm}
                setActiveForm={setActiveForm}
                onDismiss={(id) => dismissMutation.mutate(id)}
                onReopen={(id) => reopenMutation.mutate(id)}
                invalidateAfterVerb={invalidateAfterVerb}
              />
            ) : (
              <EmptyState title="No message selected" hint="Select a message to see suggested matches and triage actions." />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MessageRow({
  message,
  selected,
  threadCount,
  onClick,
}: {
  message: MailMessage
  selected: boolean
  threadCount: number
  onClick: () => void
}) {
  const isSent = message.folder === 'sent'
  const primaryLine = isSent
    ? `→ ${recipientLabel(message.to_recipients)}`
    : message.sender_name || message.sender_email || '(unknown sender)'

  return (
    <button
      onClick={onClick}
      className={cn(
        'flex w-full flex-col gap-1 border-b border-slate-100 px-3 py-2.5 text-left text-[13px] transition-colors dark:border-slate-800',
        selected ? 'bg-indigo-50 dark:bg-indigo-950/40' : 'hover:bg-slate-50 dark:hover:bg-slate-800/60',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-medium">{primaryLine}</span>
        <span className="shrink-0 text-[11px] text-slate-400">{formatTime(messageTimestamp(message))}</span>
      </div>
      <div className="min-w-0 truncate text-slate-600 dark:text-slate-300">{message.subject || '(no subject)'}</div>
      <div className="flex flex-wrap items-center gap-1">
        {message.sender_person && !isSent && <PersonChip name={message.sender_person.name} />}
        {message.has_attachments && <Paperclip size={11} className="shrink-0 text-slate-400" />}
        {threadCount >= 2 && <Badge tone="slate">×{threadCount}</Badge>}
        {(message.triage === 'linked' || message.triage === 'dismissed') && (
          <Badge tone={triageTone[message.triage]}>{message.triage}</Badge>
        )}
      </div>
    </button>
  )
}

function ReadingPane({ message }: { message: MailMessage }) {
  const mailto = mailtoHref(message)
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold break-words">{message.subject || '(no subject)'}</h2>
          {(message.triage === 'linked' || message.triage === 'dismissed') && (
            <Badge tone={triageTone[message.triage]} className="mt-1.5">
              {message.triage}
            </Badge>
          )}
        </div>
        {mailto && (
          <a
            href={mailto}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            <Reply size={13} /> Reply in Outlook
          </a>
        )}
      </div>

      <div className="space-y-1.5 text-[13px]">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="w-9 shrink-0 text-xs text-slate-400">From</span>
          {message.sender_person && <PersonChip name={message.sender_person.name} />}
          <span className="text-slate-700 dark:text-slate-200">{message.sender_name || message.sender_email || 'Unknown'}</span>
          {message.sender_email && <span className="text-xs text-slate-400">&lt;{message.sender_email}&gt;</span>}
        </div>
        {message.to_recipients.length > 0 && (
          <RecipientLine label="To" recipients={message.to_recipients} matched={message.matched_people} />
        )}
        {message.cc_recipients.length > 0 && (
          <RecipientLine label="Cc" recipients={message.cc_recipients} matched={message.matched_people} />
        )}
        <div className="flex items-center gap-1.5">
          <span className="w-9 shrink-0 text-xs text-slate-400">Date</span>
          <span className="text-slate-600 dark:text-slate-300">{fmtDateTime(messageTimestamp(message))}</span>
        </div>
      </div>

      <div className="border-t border-slate-100 pt-4 text-[13px] whitespace-pre-wrap text-slate-700 dark:border-slate-800 dark:text-slate-200">
        {message.body_text || <span className="text-slate-400">No body content.</span>}
      </div>
    </div>
  )
}

function RecipientLine({
  label,
  recipients,
  matched,
}: {
  label: string
  recipients: MailRecipient[]
  matched: { id: number; name: string; email: string | null; matched_email: string }[]
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-9 shrink-0 text-xs text-slate-400">{label}</span>
      {recipients.map((r, i) => {
        // compare against matched_email (the address that actually resolved the
        // person), not person.email — they differ on alias matches
        const match = matched.find((p) => r.email && p.matched_email === r.email.toLowerCase())
        return match ? (
          <PersonChip key={i} name={match.name} />
        ) : (
          <span key={i} className="text-slate-600 dark:text-slate-300">
            {r.name || r.email || '(unknown)'}
            {i < recipients.length - 1 ? ',' : ''}
          </span>
        )
      })}
    </div>
  )
}

// ---------- action rail ----------

const suggestionTypeTone: Record<MailSuggestion['type'], string> = { action: 'blue', commitment: 'violet' }

// a suggestion (from mail matching) or a register-picker search result — both
// shapes can sit in the same radio list and get the same hover detail
interface SelectableTarget {
  type: MailSuggestionType
  id: number
  title: string
  status: string
  due_date: string | null
  owner: PersonMini | null
  score?: number
  reasons?: string[]
}

const POPOVER_WIDTH = 288
const POPOVER_MARGIN = 8

// positioned hover/focus detail card — not the native title tooltip. Portals
// to <body> and positions with getBoundingClientRect so it can't be clipped
// by an ancestor's overflow:auto (the rail and forms all scroll), and flips
// above the anchor when there isn't room below.
function DetailPopover({ anchor, item }: { anchor: HTMLElement; item: SelectableTarget }) {
  const ref = useRef<HTMLDivElement>(null)
  // width is set from the start (not just on measure) so the very first
  // layout pass already reflects the popover's real width — otherwise its
  // height gets measured while still at native/auto width, which throws off
  // the flip-above/clamp math computed from that height. Stays hidden until
  // `place` has positioned it so it never flashes at the -9999 parking spot.
  const [style, setStyle] = useState<React.CSSProperties>({
    position: 'fixed',
    top: -9999,
    left: -9999,
    width: POPOVER_WIDTH,
    visibility: 'hidden',
  })

  useLayoutEffect(() => {
    const place = () => {
      const rect = anchor.getBoundingClientRect()
      const popH = ref.current?.offsetHeight ?? 0
      let left = rect.left
      if (left + POPOVER_WIDTH > window.innerWidth - POPOVER_MARGIN) left = window.innerWidth - POPOVER_WIDTH - POPOVER_MARGIN
      if (left < POPOVER_MARGIN) left = POPOVER_MARGIN
      const spaceBelow = window.innerHeight - rect.bottom
      const showAbove = spaceBelow < popH + POPOVER_MARGIN && rect.top > popH + POPOVER_MARGIN
      const top = showAbove ? Math.max(POPOVER_MARGIN, rect.top - popH - 6) : rect.bottom + 6
      setStyle({ position: 'fixed', left, top, width: POPOVER_WIDTH, visibility: 'visible' })
    }
    place()
    // capture=true so scrolling any ancestor container (the rail/pane/form
    // columns are all overflow-y-auto, not just window) re-runs the layout
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [anchor, item])

  return createPortal(
    <div
      ref={ref}
      role="tooltip"
      style={style}
      className="z-50 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-800"
    >
      <div className="flex items-center gap-1.5">
        <Badge tone={suggestionTypeTone[item.type]}>{item.type}</Badge>
        <Badge tone={statusTone[item.status] ?? 'slate'}>{item.status.replace('_', ' ')}</Badge>
      </div>
      <p className="mt-1.5 font-medium break-words">{item.title}</p>
      <dl className="mt-1.5 space-y-0.5 text-slate-500 dark:text-slate-400">
        <div>Owner: {item.owner ? item.owner.name : 'Unassigned'}</div>
        <div>Due: {item.due_date ? fmtDate(item.due_date) : '—'}</div>
        {item.score != null && <div>Score: {item.score}</div>}
      </dl>
      {item.reasons && item.reasons.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-slate-500 dark:text-slate-400">
          {item.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}
    </div>,
    document.body,
  )
}

// wraps a suggestion/picker row so hovering or keyboard-focusing it shows the
// full detail popover; closes on mouseleave, blur (to outside this row) or Escape
function HoverDetailTarget({
  item,
  className,
  focusable,
  children,
}: {
  item: SelectableTarget
  className?: string
  focusable?: boolean
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div
      ref={ref}
      data-hover-target
      tabIndex={focusable ? 0 : undefined}
      className={className}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!ref.current?.contains(e.relatedTarget as Node)) setOpen(false)
      }}
    >
      {children}
      {open && ref.current && <DetailPopover anchor={ref.current} item={item} />}
    </div>
  )
}

function VerbButton({
  active,
  onClick,
  keyHint,
  children,
  className,
}: {
  active?: boolean
  onClick: () => void
  keyHint: string
  children: ReactNode
  className?: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs font-medium transition-colors',
        active
          ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-950/40 dark:text-indigo-300'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800',
        className,
      )}
    >
      {children}
      <kbd className="ml-auto rounded border border-slate-300 bg-slate-50 px-1 text-[10px] text-slate-400 dark:border-slate-600 dark:bg-slate-800">
        {keyHint}
      </kbd>
    </button>
  )
}

function FormShell({ title, onCancel, children }: { title: string; onCancel: () => void; children: ReactNode }) {
  return (
    <div className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/40 p-3 dark:border-indigo-900 dark:bg-indigo-950/30">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-300">{title}</h4>
        <button onClick={onCancel} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
          <X size={13} />
        </button>
      </div>
      {children}
    </div>
  )
}

function SuggestionRow({ s }: { s: MailSuggestion }) {
  return (
    <HoverDetailTarget
      item={s}
      focusable
      className="rounded-lg border border-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-800"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Badge tone={suggestionTypeTone[s.type]}>{s.type}</Badge>
          <span className="min-w-0 truncate text-[13px] font-medium">{s.title}</span>
        </div>
        {s.due_date && <span className="shrink-0 text-[11px] text-slate-400">{fmtDate(s.due_date)}</span>}
      </div>
      <div className="mt-1 text-[11px] text-slate-400">
        {s.owner ? s.owner.name : 'Unassigned'} · {s.status}
      </div>
      {s.reasons.length > 0 && <p className="mt-1 truncate text-[11px] text-slate-400 italic">{s.reasons.join(' · ')}</p>}
    </HoverDetailTarget>
  )
}

// register-picker query, debounced ~250ms, only fires at 2+ chars — mirrors
// GlobalSearch's own debounce/min-length convention
function useRegisterPicker(query: string) {
  const debounced = useDebouncedValue(query, 250)
  const trimmed = debounced.trim()
  const queried = trimmed.length >= 2
  const { data, isFetching } = useQuery({
    queryKey: ['register-picker', trimmed],
    queryFn: () => registerPicker(trimmed),
    enabled: queried,
    placeholderData: (previous) => previous,
  })
  return { items: queried ? (data?.items ?? []) : [], isFetching: queried && isFetching, queried, trimmed }
}

// "Search all open items…" below a suggestions list — same radio-select
// mechanics as the suggestions themselves, just sourced from the picker API
// instead of the mail-matching heuristics
function TargetPicker({
  name,
  filterType,
  exclude,
  selectedKey,
  pickedItem,
  onSelect,
}: {
  name: string
  filterType?: MailSuggestionType
  exclude: Set<string>
  selectedKey: string
  pickedItem: RegisterPickerItem | null
  onSelect: (item: RegisterPickerItem) => void
}) {
  const [query, setQuery] = useState('')
  const { items, isFetching, queried, trimmed } = useRegisterPicker(query)
  const results = items.filter((item) => (!filterType || item.type === filterType) && !exclude.has(`${item.type}-${item.id}`))

  // a target picked against an earlier query can fall out of the results
  // once the search is refined further — pin it above the list so the
  // (still-enabled) submit button stays explained instead of silently
  // pointing at something the user can no longer see
  const pickedKey = pickedItem ? `${pickedItem.type}-${pickedItem.id}` : null
  const showPinned =
    pickedItem != null && selectedKey === pickedKey && !results.some((item) => `${item.type}-${item.id}` === pickedKey)

  return (
    <div className="space-y-1.5">
      <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search all open items…" />
      {showPinned && pickedItem && (
        <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50/60 px-2.5 py-1.5 text-xs dark:border-indigo-900 dark:bg-indigo-950/30">
          <Badge tone={suggestionTypeTone[pickedItem.type]}>{pickedItem.type}</Badge>
          <span className="min-w-0 flex-1 truncate">Selected: {pickedItem.title}</span>
        </div>
      )}
      {queried && !isFetching && results.length === 0 && (
        <p className="text-[11px] text-slate-400">No open items match "{trimmed}".</p>
      )}
      {results.map((item) => (
        <HoverDetailTarget key={`${item.type}-${item.id}`} item={item}>
          <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs dark:border-slate-800">
            <input
              type="radio"
              name={name}
              checked={selectedKey === `${item.type}-${item.id}`}
              onChange={() => onSelect(item)}
            />
            <Badge tone={suggestionTypeTone[item.type]}>{item.type}</Badge>
            <span className="min-w-0 flex-1 truncate">{item.title}</span>
          </label>
        </HoverDetailTarget>
      ))}
    </div>
  )
}

function LogChaseForm({
  message,
  suggestions,
  onCancel,
  onDone,
}: {
  message: MailMessage
  suggestions: MailSuggestion[]
  onCancel: () => void
  onDone: () => void
}) {
  const [targetKey, setTargetKey] = useState('')
  const [pickedTarget, setPickedTarget] = useState<RegisterPickerItem | null>(null)
  const [note, setNote] = useState(`Chased via email: ${message.subject || '(no subject)'}`)
  const [nextChaseOn, setNextChaseOn] = useState(() => new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10))

  useEffect(() => {
    if (!targetKey && suggestions.length) setTargetKey(`${suggestions[0].type}-${suggestions[0].id}`)
  }, [suggestions, targetKey])

  const suggestionMatch = suggestions.find((s) => `${s.type}-${s.id}` === targetKey)
  const target: SelectableTarget | undefined =
    suggestionMatch ?? (pickedTarget && `${pickedTarget.type}-${pickedTarget.id}` === targetKey ? pickedTarget : undefined)
  const suggestionKeys = useMemo(() => new Set(suggestions.map((s) => `${s.type}-${s.id}`)), [suggestions])

  const mutation = useMutation({
    mutationFn: () => {
      if (!target) throw new Error('Pick a target first')
      return mailLogChase(message.id, {
        target_type: target.type,
        target_id: target.id,
        note: note.trim() || null,
        next_chase_on: nextChaseOn || null,
      })
    },
    onSuccess: () => {
      toast.success(`Chase logged${target ? ` — ${target.title}` : ''}`)
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <FormShell title="Log chase" onCancel={onCancel}>
      {suggestions.length === 0 ? (
        <p className="text-xs text-slate-400">No suggested action/commitment — search for one below.</p>
      ) : (
        <div className="space-y-1.5">
          {suggestions.map((s) => (
            <HoverDetailTarget key={`${s.type}-${s.id}`} item={s}>
              <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs dark:border-slate-800">
                <input
                  type="radio"
                  name="chase-target"
                  checked={targetKey === `${s.type}-${s.id}`}
                  onChange={() => setTargetKey(`${s.type}-${s.id}`)}
                />
                <Badge tone={suggestionTypeTone[s.type]}>{s.type}</Badge>
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
              </label>
            </HoverDetailTarget>
          ))}
        </div>
      )}
      <TargetPicker
        name="chase-target"
        exclude={suggestionKeys}
        selectedKey={targetKey}
        pickedItem={pickedTarget}
        onSelect={(item) => {
          setPickedTarget(item)
          setTargetKey(`${item.type}-${item.id}`)
        }}
      />
      <Field label="Note (optional)">
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Field label="Next chase on">
        <Input type="date" value={nextChaseOn} onChange={(e) => setNextChaseOn(e.target.value)} />
      </Field>
      <div className="flex justify-end">
        <Button size="sm" disabled={!target || mutation.isPending} onClick={() => mutation.mutate()}>
          Log chase
        </Button>
      </div>
    </FormShell>
  )
}

function NewActionForm({ message, onCancel, onDone }: { message: MailMessage; onCancel: () => void; onDone: () => void }) {
  const [text, setText] = useState(() => quickAddPrefill(message))

  const mutation = useMutation({
    mutationFn: () => mailCreateAction(message.id, text),
    onSuccess: (res) => {
      toast.success(`Action created: ${res.title}`, {
        description: res.warnings.length ? res.warnings.join('; ') : undefined,
      })
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <FormShell title="New action" onCancel={onCancel}>
      <Input
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder='Chase scope pack @sarah due:+7'
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            if (text.trim()) mutation.mutate()
          }
        }}
      />
      <p className="text-[11px] text-slate-400">
        Grammar: @person #workstream due:VALUE !priority — same as quick add.
      </p>
      <div className="flex justify-end">
        <Button size="sm" disabled={!text.trim() || mutation.isPending} onClick={() => mutation.mutate()}>
          Create action
        </Button>
      </div>
    </FormShell>
  )
}

function CloseActionForm({
  message,
  suggestions,
  onCancel,
  onDone,
}: {
  message: MailMessage
  suggestions: MailSuggestion[]
  onCancel: () => void
  onDone: () => void
}) {
  const [targetId, setTargetId] = useState<number | null>(null)
  const [pickedTarget, setPickedTarget] = useState<RegisterPickerItem | null>(null)

  useEffect(() => {
    if (targetId == null && suggestions.length) setTargetId(suggestions[0].id)
  }, [suggestions, targetId])

  const mutation = useMutation({
    mutationFn: () => {
      if (targetId == null) throw new Error('Pick an action first')
      return mailCloseAction(message.id, targetId)
    },
    onSuccess: () => {
      toast.success('Marked done — email kept as evidence')
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const suggestionKeys = useMemo(() => new Set(suggestions.map((s) => `action-${s.id}`)), [suggestions])

  return (
    <FormShell title="Close action" onCancel={onCancel}>
      {suggestions.length === 0 ? (
        <p className="text-xs text-slate-400">No suggested action — search for one below.</p>
      ) : (
        <div className="space-y-1.5">
          {suggestions.map((s) => (
            <HoverDetailTarget key={s.id} item={s}>
              <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs dark:border-slate-800">
                <input type="radio" name="close-target" checked={targetId === s.id} onChange={() => setTargetId(s.id)} />
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
              </label>
            </HoverDetailTarget>
          ))}
        </div>
      )}
      <TargetPicker
        name="close-target"
        filterType="action"
        exclude={suggestionKeys}
        selectedKey={targetId != null ? `action-${targetId}` : ''}
        pickedItem={pickedTarget}
        onSelect={(item) => {
          setPickedTarget(item)
          setTargetId(item.id)
        }}
      />
      <div className="flex justify-end">
        <Button size="sm" disabled={targetId == null || mutation.isPending} onClick={() => mutation.mutate()}>
          Mark done — email kept as evidence
        </Button>
      </div>
    </FormShell>
  )
}

function PeopleNoteForm({ message, onCancel, onDone }: { message: MailMessage; onCancel: () => void; onDone: () => void }) {
  const { data: people = [] } = useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/people') })
  const defaultPersonId = message.sender_person?.id ?? message.matched_people[0]?.id ?? null
  const [personId, setPersonId] = useState(defaultPersonId != null ? String(defaultPersonId) : '')
  const [kind, setKind] = useState<PersonNoteKind>('general')
  const [note, setNote] = useState('')

  const mutation = useMutation({
    mutationFn: () => {
      if (!personId) throw new Error('Pick a person first')
      return mailPersonNote(message.id, { person_id: Number(personId), kind, note })
    },
    onSuccess: () => {
      toast.success('Note added')
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <FormShell title="People note" onCancel={onCancel}>
      <Field label="Person">
        <Select value={personId} onChange={(e) => setPersonId(e.target.value)}>
          <option value="">Choose…</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Kind">
        <Select value={kind} onChange={(e) => setKind(e.target.value as PersonNoteKind)}>
          <option value="general">General</option>
          <option value="call">Call</option>
          <option value="feedback">Feedback</option>
          <option value="observation">Observation</option>
        </Select>
      </Field>
      <Field label="Note">
        <Textarea
          autoFocus
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What's worth remembering about this person?"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
              e.preventDefault()
              if (note.trim() && personId) mutation.mutate()
            }
          }}
        />
      </Field>
      <div className="flex justify-end">
        <Button size="sm" disabled={!note.trim() || !personId || mutation.isPending} onClick={() => mutation.mutate()}>
          Add note
        </Button>
      </div>
    </FormShell>
  )
}

function ActionRail({
  message,
  activeForm,
  setActiveForm,
  onDismiss,
  onReopen,
  invalidateAfterVerb,
}: {
  message: MailMessage
  activeForm: ActiveForm
  setActiveForm: (f: ActiveForm) => void
  onDismiss: (id: number) => void
  onReopen: (id: number) => void
  invalidateAfterVerb: (id: number) => void
}) {
  const { data: suggestionsData, isLoading: suggestionsLoading } = useQuery({
    queryKey: ['mail-suggestions', message.id],
    queryFn: () => mailSuggestions(message.id),
  })
  const suggestions = suggestionsData?.suggestions ?? []
  const isPending = message.triage === 'pending'

  const cancel = () => setActiveForm(null)
  const done = () => {
    setActiveForm(null)
    invalidateAfterVerb(message.id)
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold">Act on this message</h3>

      <Section title="Suggested matches">
        {suggestionsLoading ? (
          <Spinner />
        ) : suggestions.length === 0 ? (
          <p className="text-xs text-slate-400">No obvious matches — create a new action or dismiss.</p>
        ) : (
          <div className="space-y-1.5">
            {suggestions.map((s) => (
              <SuggestionRow key={`${s.type}-${s.id}`} s={s} />
            ))}
          </div>
        )}
      </Section>

      <div className="grid grid-cols-2 gap-2">
        <VerbButton active={activeForm === 'chase'} onClick={() => setActiveForm(activeForm === 'chase' ? null : 'chase')} keyHint="C">
          <PhoneCall size={13} /> Log chase
        </VerbButton>
        <VerbButton active={activeForm === 'action'} onClick={() => setActiveForm(activeForm === 'action' ? null : 'action')} keyHint="A">
          <Plus size={13} /> New action
        </VerbButton>
        <VerbButton active={activeForm === 'close'} onClick={() => setActiveForm(activeForm === 'close' ? null : 'close')} keyHint="X">
          <CheckCircle2 size={13} /> Close action
        </VerbButton>
        <VerbButton active={activeForm === 'note'} onClick={() => setActiveForm(activeForm === 'note' ? null : 'note')} keyHint="N">
          <StickyNote size={13} /> People note
        </VerbButton>
        {isPending ? (
          <VerbButton onClick={() => onDismiss(message.id)} keyHint="E" className="col-span-2 justify-center">
            <EyeOff size={13} /> Dismiss
          </VerbButton>
        ) : (
          <VerbButton onClick={() => onReopen(message.id)} keyHint="Z" className="col-span-2 justify-center">
            <RotateCcw size={13} /> Reopen
          </VerbButton>
        )}
      </div>

      {activeForm === 'chase' && <LogChaseForm message={message} suggestions={suggestions} onCancel={cancel} onDone={done} />}
      {activeForm === 'action' && <NewActionForm message={message} onCancel={cancel} onDone={done} />}
      {activeForm === 'close' && (
        <CloseActionForm
          message={message}
          suggestions={suggestions.filter((s) => s.type === 'action')}
          onCancel={cancel}
          onDone={done}
        />
      )}
      {activeForm === 'note' && <PeopleNoteForm message={message} onCancel={cancel} onDone={done} />}
    </div>
  )
}
