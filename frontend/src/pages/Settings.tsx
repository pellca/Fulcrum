import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Database, Download, Eraser, FileUp, Sprout } from 'lucide-react'
import { api } from '../api'
import { Button, Card, Field, Input, PageHeader, Select } from '../components/ui'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.get<Record<string, number>>('/admin/stats'),
  })
  const [scope, setScope] = useState('demo')
  const [confirmText, setConfirmText] = useState('')

  const seed = useMutation({
    mutationFn: () => api.post<Record<string, number>>('/admin/seed'),
    onSuccess: (res) => {
      toast.success('Demo data loaded', {
        description: Object.entries(res)
          .map(([k, v]) => `${v} ${k}`)
          .join(', '),
      })
      queryClient.invalidateQueries()
    },
  })

  const clear = useMutation({
    mutationFn: () => api.post('/admin/clear', { scope, confirm: confirmText }),
    onSuccess: () => {
      toast.success(`Cleared: ${scope}`)
      setConfirmText('')
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div>
      <PageHeader title="Settings" subtitle="Data management, backups, and demo mode" />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title={<span className="flex items-center gap-1.5"><Database size={14} /> Your data</span>}>
          <div className="mb-4 grid grid-cols-3 gap-2 text-center">
            {stats &&
              Object.entries(stats)
                .filter(([, count]) => count > 0)
                .map(([table, count]) => (
                  <div key={table} className="rounded-lg bg-slate-50 px-2 py-2 dark:bg-slate-800/60">
                    <div className="text-lg font-bold">{count}</div>
                    <div className="text-[10px] text-slate-500">{table.replace('_', ' ')}</div>
                  </div>
                ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/api/admin/backup" download>
              <Button variant="secondary">
                <Download size={15} /> Download database backup
              </Button>
            </a>
            <a href="/api/admin/export.json" download>
              <Button variant="secondary">
                <FileUp size={15} /> Export everything as JSON
              </Button>
            </a>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            The whole platform lives in one SQLite file (<code>data/fulcrum.db</code>). Back it up before
            experiments; restoring is just putting the file back.
          </p>
        </Card>

        <Card title={<span className="flex items-center gap-1.5"><Sprout size={14} /> Demo data</span>}>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Load a realistic Internal Audit &amp; Investigations scenario (people, workstreams, commitments,
            meetings, a dependency chain, key dates). Every demo row is flagged, so it can be removed at any
            time without touching your real data.
          </p>
          <Button onClick={() => seed.mutate()} disabled={seed.isPending}>
            <Sprout size={15} /> Load demo data
          </Button>
        </Card>

        <Card title={<span className="flex items-center gap-1.5"><Eraser size={14} /> Clear data</span>} className="xl:col-span-2">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="What to clear">
              <Select value={scope} onChange={(e) => setScope(e.target.value)} className="!w-64">
                <option value="demo">Demo data only (real data untouched)</option>
                <option value="diary">Imported diary events only</option>
                <option value="module_runs">Module run history only</option>
                <option value="all">Everything — full reset</option>
              </Select>
            </Field>
            <Field label='Type "CLEAR" to confirm'>
              <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} className="!w-40" placeholder="CLEAR" />
            </Field>
            <Button
              variant="danger"
              disabled={confirmText !== 'CLEAR' || clear.isPending}
              onClick={() => clear.mutate()}
            >
              <Eraser size={15} /> Clear {scope === 'all' ? 'everything' : scope.replace('_', ' ')}
            </Button>
          </div>
          {scope === 'all' && (
            <p className="mt-3 text-xs font-medium text-rose-500">
              This wipes every table and recreates an empty database. Download a backup first.
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}
