import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Play, Puzzle, RefreshCw } from 'lucide-react'
import { api, type ModuleManifest, type ModuleRun } from '../api'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  fmtDateTime,
  Input,
  PageHeader,
  Spinner,
  StatusBadge,
} from '../components/ui'

export default function Modules() {
  const queryClient = useQueryClient()
  const { data: modules, isLoading } = useQuery({
    queryKey: ['modules'],
    queryFn: () => api.get<ModuleManifest[]>('/modules'),
  })
  const { data: runs = [] } = useQuery({
    queryKey: ['module-runs'],
    queryFn: () => api.get<ModuleRun[]>('/modules/runs'),
    refetchInterval: (query) =>
      query.state.data?.some((run) => run.status === 'running') ? 1500 : false,
  })
  const [args, setArgs] = useState<Record<string, Record<string, string>>>({})
  const [expandedRun, setExpandedRun] = useState<number | null>(null)

  const run = useMutation({
    mutationFn: (name: string) => api.post<{ run_id: number }>(`/modules/${name}/run`, { args: args[name] ?? {} }),
    onSuccess: (res) => {
      toast.success(`Run #${res.run_id} started`)
      setExpandedRun(res.run_id)
      queryClient.invalidateQueries({ queryKey: ['module-runs'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Modules"
        subtitle="Your registered tools — run them here, their output feeds the platform"
      />
      <div className="mb-5 grid gap-3 xl:grid-cols-2">
        {(modules ?? []).map((mod) => (
          <Card key={mod.name} title={<span className="flex items-center gap-1.5"><Puzzle size={14} /> {mod.label ?? mod.name}</span>}
            actions={!mod.available ? <Badge tone="amber">requires {mod.platform}</Badge> : undefined}
          >
            {mod.error ? (
              <p className="text-xs text-rose-500">Manifest error: {mod.error}</p>
            ) : (
              <>
                {mod.description && <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">{mod.description}</p>}
                <div className="space-y-2">
                  {mod.args.map((arg) => (
                    <Field key={arg.name} label={`${arg.label ?? arg.name}${arg.required ? ' *' : ''}`}>
                      <Input
                        value={args[mod.name]?.[arg.name] ?? arg.default ?? ''}
                        onChange={(e) =>
                          setArgs((a) => ({ ...a, [mod.name]: { ...a[mod.name], [arg.name]: e.target.value } }))
                        }
                      />
                    </Field>
                  ))}
                </div>
                <Button
                  className="mt-3"
                  size="sm"
                  disabled={!mod.available || run.isPending}
                  onClick={() => {
                    // seed defaults for args the user hasn't touched
                    const merged: Record<string, string> = {}
                    for (const arg of mod.args) merged[arg.name] = args[mod.name]?.[arg.name] ?? arg.default ?? ''
                    setArgs((a) => ({ ...a, [mod.name]: merged }))
                    setTimeout(() => run.mutate(mod.name), 0)
                  }}
                >
                  <Play size={13} /> Run
                </Button>
              </>
            )}
          </Card>
        ))}
        {!modules?.length && (
          <div className="xl:col-span-2">
            <EmptyState
              icon={<Puzzle size={28} />}
              title="No modules registered"
              hint="Drop a manifest JSON into modules/registry/ describing the command to run — see the README for the format."
            />
          </div>
        )}
      </div>

      <Card
        title="Run history"
        actions={
          <Button size="sm" variant="ghost" onClick={() => queryClient.invalidateQueries({ queryKey: ['module-runs'] })}>
            <RefreshCw size={13} /> Refresh
          </Button>
        }
      >
        {runs.length === 0 ? (
          <EmptyState title="No runs yet" />
        ) : (
          <div className="space-y-1.5">
            {runs.map((moduleRun) => (
              <div key={moduleRun.id} className="rounded-lg border border-slate-100 dark:border-slate-800">
                <button
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
                  onClick={() => setExpandedRun((r) => (r === moduleRun.id ? null : moduleRun.id))}
                >
                  <span className="flex items-center gap-2 text-[13px]">
                    <span className="font-mono text-xs text-slate-400">#{moduleRun.id}</span>
                    <span className="font-medium">{moduleRun.module_name}</span>
                    <StatusBadge status={moduleRun.status} />
                  </span>
                  <span className="text-xs text-slate-500">{fmtDateTime(moduleRun.started_at)}</span>
                </button>
                {expandedRun === moduleRun.id && (
                  <pre className="max-h-64 overflow-auto border-t border-slate-100 bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-200 dark:border-slate-800">
                    {moduleRun.log || '(no output yet)'}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
