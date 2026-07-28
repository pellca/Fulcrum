import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, ClipboardCopy, FileUp, X } from 'lucide-react'
import { api, type Meeting } from '../api'
import { Badge, Button, Field, fmtDate, Modal, Select, cn } from './ui'

interface PreviewItem {
  type: 'action' | 'commitment'
  title: string
  description: string | null
  owner_id: number | null
  owner_name: string | null
  owner_matched: boolean
  workstream_id: number | null
  workstream_name: string | null
  due_date: string | null
  status: string
  priority: string
  origin: string
  meeting_id: number | null
  meeting_label: string | null
  meeting_matched: boolean
}

interface Preview {
  columns: Record<string, string>
  items: PreviewItem[]
  skipped: number
}

export function CopyCopilotPromptButton() {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    const res = await fetch('/api/imports/copilot-prompt')
    const text = await res.text()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Copilot prompt copied', {
      description: 'Paste it into Copilot in the Teams meeting; it returns a CSV ready for Import.',
    })
    setTimeout(() => setCopied(false), 2500)
  }
  return (
    <Button variant="secondary" onClick={copy} title="Copies a Teams Copilot prompt that extracts this meeting's actions & commitments as an importable CSV — personalised with your people, workstreams and forums">
      {copied ? <Check size={15} className="text-emerald-500" /> : <ClipboardCopy size={15} />}
      Copilot prompt
    </Button>
  )
}

export function ImportCsvButton() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [defaultMeeting, setDefaultMeeting] = useState('')
  const queryClient = useQueryClient()

  const { data: meetings = [] } = useQuery({
    queryKey: ['meetings', 'all'],
    queryFn: () => api.get<Meeting[]>('/meetings'),
    enabled: preview !== null,
  })

  const upload = useMutation({
    mutationFn: (file: File) => api.upload<Preview>('/imports/planner/preview', file),
    onSuccess: (result) => {
      if (!result.items.length) {
        toast.error('No importable rows found in that file')
        return
      }
      setPreview(result)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const commit = useMutation({
    mutationFn: () =>
      api.post<{ created: { actions: number; commitments: number; meeting_links: number } }>(
        '/imports/planner/commit',
        { items: preview!.items, default_meeting_id: defaultMeeting ? Number(defaultMeeting) : null },
      ),
    onSuccess: ({ created }) => {
      toast.success(`Imported ${created.actions} actions, ${created.commitments} commitments`, {
        description: created.meeting_links ? `${created.meeting_links} linked to their source meeting.` : undefined,
      })
      setPreview(null)
      setDefaultMeeting('')
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const rowsWithoutMeeting = preview?.items.filter((i) => !i.meeting_id).length ?? 0

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.xlsx,.xlsm"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload.mutate(file)
          e.target.value = ''
        }}
      />
      <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
        <FileUp size={15} /> {upload.isPending ? 'Reading…' : 'Import CSV'}
      </Button>

      {preview && (
        <Modal open onClose={() => setPreview(null)} title={`Import preview — ${preview.items.length} items`} wide>
          <div className="mb-3 max-h-80 overflow-auto rounded-lg border border-slate-200 dark:border-slate-700">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                <tr className="text-slate-500 dark:text-slate-400">
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Title</th>
                  <th className="px-3 py-2 font-medium">Owner</th>
                  <th className="px-3 py-2 font-medium">Workstream</th>
                  <th className="px-3 py-2 font-medium">Due</th>
                  <th className="px-3 py-2 font-medium">Priority</th>
                  <th className="px-3 py-2 font-medium">Meeting</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {preview.items.map((item, index) => (
                  <tr key={index}>
                    <td className="px-3 py-2">
                      <Badge tone={item.type === 'commitment' ? 'indigo' : 'blue'}>{item.type}</Badge>
                    </td>
                    <td className="max-w-56 truncate px-3 py-2 font-medium" title={item.description ?? undefined}>
                      {item.title}
                    </td>
                    <td className={cn('px-3 py-2 whitespace-nowrap', !item.owner_matched && 'text-amber-600 dark:text-amber-400')}>
                      {item.owner_name ?? '—'}
                      {!item.owner_matched && <X size={11} className="ml-1 inline" aria-label="No matching person" />}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{item.workstream_name ?? '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{fmtDate(item.due_date)}</td>
                    <td className="px-3 py-2">{item.priority}</td>
                    <td className={cn('max-w-40 truncate px-3 py-2', !item.meeting_matched && 'text-amber-600 dark:text-amber-400')}>
                      {item.meeting_label ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            {preview.skipped > 0 && <>Skipped {preview.skipped} row(s) without a title. </>}
            Owners in amber didn't match a known person — the name is kept but unassigned.
          </p>
          {rowsWithoutMeeting > 0 && (
            <Field label={`Attach the ${rowsWithoutMeeting} row(s) without a source meeting to:`}>
              <Select value={defaultMeeting} onChange={(e) => setDefaultMeeting(e.target.value)}>
                <option value="">Don't attach</option>
                {meetings.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.forum.name} — {new Date(m.scheduled_at).toLocaleDateString('en-GB')}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPreview(null)}>
              Cancel
            </Button>
            <Button onClick={() => commit.mutate()} disabled={commit.isPending}>
              Import {preview.items.length} items
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
