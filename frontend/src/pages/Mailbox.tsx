import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FolderOpen, Paperclip, Upload, UserRound } from 'lucide-react'
import {
  importMailPath,
  importMailUpload,
  listMailMessages,
  mailStats,
  type MailFolder,
  type MailMessage,
  type MailRecipient,
  type MailTriage,
} from '../api'
import { Badge, Button, cn, EmptyState, fmtDateTime, Input, PageHeader, Spinner } from '../components/ui'

type FolderFilter = 'all' | MailFolder
type TriageFilter = 'all' | MailTriage

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

export default function Mailbox() {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [days, setDays] = useState<number>(5)
  const [folder, setFolder] = useState<FolderFilter>('all')
  const [triage, setTriage] = useState<TriageFilter>('pending')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [importPath, setImportPath] = useState('')

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

  const importSuccess = (summary: { added: number; updated: number; purged: number }) => {
    toast.success(`Mail imported: ${summary.added} added, ${summary.updated} updated`, {
      description: summary.purged ? `${summary.purged} message(s) purged past retention.` : undefined,
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

  const selected = messages.find((m) => m.id === selectedId) ?? null

  // j/k or arrow up/down moves selection — ignored while a form field has focus
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const tag = (document.activeElement?.tagName ?? '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (e.key !== 'j' && e.key !== 'k' && e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      if (messages.length === 0) return
      e.preventDefault()
      const down = e.key === 'j' || e.key === 'ArrowDown'
      const currentIndex = messages.findIndex((m) => m.id === selectedId)
      const nextIndex =
        currentIndex === -1 ? 0 : down ? Math.min(currentIndex + 1, messages.length - 1) : Math.max(currentIndex - 1, 0)
      setSelectedId(messages[nextIndex].id)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [messages, selectedId])

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
      ) : messages.length === 0 ? (
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
                onClick={() => setSelectedId(m.id)}
              />
            ))}
          </div>
          <div className="h-[70vh] min-w-0 flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            {selected ? (
              <ReadingPane message={selected} />
            ) : (
              <EmptyState title="Select a message" hint="Pick something from the list on the left — j/k or the arrow keys move the selection." />
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
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold break-words">{message.subject || '(no subject)'}</h2>
        {(message.triage === 'linked' || message.triage === 'dismissed') && (
          <Badge tone={triageTone[message.triage]} className="mt-1.5">
            {message.triage}
          </Badge>
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
