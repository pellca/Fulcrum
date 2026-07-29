import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileUp } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Modal } from './ui'

interface PersonPreviewItem {
  name: string
  email: string | null
  team: string | null
  role: string | null
  is_bpm: boolean
  aliases: string[]
  exists: boolean
  existing_name: string | null
}

interface PeoplePreview {
  items: PersonPreviewItem[]
  skipped: number
}

export function PeopleImportButton() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<PeoplePreview | null>(null)
  const queryClient = useQueryClient()

  const upload = useMutation({
    mutationFn: (file: File) => api.upload<PeoplePreview>('/imports/people/preview', file),
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
      api.post<{ created: number; skipped_existing: number; aliases_added: number }>(
        '/imports/people/commit',
        { items: preview!.items },
      ),
    onSuccess: (result) => {
      toast.success(`${result.created} people added`, {
        description:
          `${result.skipped_existing} already existed` +
          (result.aliases_added ? ` · ${result.aliases_added} aliases added` : ''),
      })
      setPreview(null)
      queryClient.invalidateQueries({ queryKey: ['people'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const newCount = preview?.items.filter((i) => !i.exists).length ?? 0

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
      <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
        <FileUp size={15} /> {upload.isPending ? 'Reading…' : 'Import CSV'}
      </Button>

      {preview && (
        <Modal open onClose={() => setPreview(null)} title={`Import people — ${newCount} new of ${preview.items.length}`} wide>
          <div className="mb-3 max-h-80 overflow-auto rounded-lg border border-slate-200 dark:border-slate-700">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                <tr className="text-slate-500 dark:text-slate-400">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Role</th>
                  <th className="px-3 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Aliases</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {preview.items.map((item) => (
                  <tr key={item.name} className={item.exists ? 'opacity-60' : ''}>
                    <td className="px-3 py-2 font-medium whitespace-nowrap">
                      {item.name}
                      {item.is_bpm && <Badge tone="indigo" className="ml-1.5">BPM</Badge>}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{item.role ?? '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{item.team ?? '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{item.email ?? '—'}</td>
                    <td className="max-w-40 truncate px-3 py-2">{item.aliases.join('; ') || '—'}</td>
                    <td className="px-3 py-2">
                      {item.exists ? <Badge tone="slate">exists — aliases only</Badge> : <Badge tone="green">new</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            {preview.skipped > 0 && <>Skipped {preview.skipped} row(s) (no name or duplicate). </>}
            Existing people are never overwritten — only missing aliases are added to them.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPreview(null)}>
              Cancel
            </Button>
            <Button onClick={() => commit.mutate()} disabled={commit.isPending}>
              Import
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
