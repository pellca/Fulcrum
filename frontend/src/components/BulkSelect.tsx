import { useCallback, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { Button, Modal, cn } from './ui'

export type Id = number | string

/** Checkbox selection state for a list, with shift-free select-all semantics. */
export function useSelection() {
  const [selected, setSelected] = useState<Set<Id>>(new Set())

  const toggle = useCallback((id: Id) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback((ids: Id[]) => {
    setSelected((current) => (ids.every((id) => current.has(id)) ? new Set() : new Set(ids)))
  }, [])

  const clear = useCallback(() => setSelected(new Set()), [])

  return { selected, toggle, toggleAll, clear, count: selected.size }
}

export function SelectCheckbox({
  checked,
  onChange,
  label,
  indeterminate,
}: {
  checked: boolean
  onChange: () => void
  label: string
  indeterminate?: boolean
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = Boolean(indeterminate) && !checked
      }}
      onChange={onChange}
      onClick={(e) => e.stopPropagation()}
      aria-label={label}
      className="h-3.5 w-3.5 cursor-pointer rounded accent-indigo-600"
    />
  )
}

interface CheckResult {
  type: string
  label: string
  found: number
  titles: string[]
  warnings: { label: string; count: number; examples: string[] }[]
}

/**
 * Floating bar shown while rows are selected. Delete runs a server-side preflight
 * first so the user sees what would be orphaned before confirming.
 */
export function BulkBar({
  type,
  ids,
  onClear,
  extraActions,
}: {
  type: string
  ids: Id[]
  onClear: () => void
  extraActions?: React.ReactNode
}) {
  const queryClient = useQueryClient()
  const [check, setCheck] = useState<CheckResult | null>(null)

  const preflight = useMutation({
    mutationFn: () => api.post<CheckResult>('/bulk/check', { type, ids }),
    onSuccess: setCheck,
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: () => api.post<{ deleted: number; links_removed: number }>('/bulk/delete', { type, ids }),
    onSuccess: (result) => {
      toast.success(`Deleted ${result.deleted} ${check?.label ?? 'items'}`, {
        description: result.links_removed ? `${result.links_removed} links cleaned up.` : undefined,
      })
      setCheck(null)
      onClear()
      queryClient.invalidateQueries()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (ids.length === 0) return null

  return (
    <>
      <div className="no-print fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <span className="text-[13px] font-medium">
          {ids.length} selected
        </span>
        {extraActions}
        <Button size="sm" variant="danger" onClick={() => preflight.mutate()} disabled={preflight.isPending}>
          <Trash2 size={13} /> Delete
        </Button>
        <button onClick={onClear} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Clear selection">
          <X size={15} />
        </button>
      </div>

      {check && (
        <Modal open onClose={() => setCheck(null)} title={`Delete ${check.found} ${check.label}?`}>
          <div className="space-y-3">
            <ul className="max-h-40 space-y-0.5 overflow-y-auto rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
              {check.titles.map((title, i) => (
                <li key={i} className="truncate">
                  {title}
                </li>
              ))}
              {check.found > check.titles.length && (
                <li className="text-slate-400">…and {check.found - check.titles.length} more</li>
              )}
            </ul>

            {check.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-300 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-amber-800 dark:text-amber-300">
                  <AlertTriangle size={13} /> This will also affect:
                </p>
                <ul className="space-y-1 text-xs">
                  {check.warnings.map((warning) => (
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
                {check.type === 'person' && (
                  <p className="mt-2 text-[11px] text-amber-800 dark:text-amber-300">
                    Those items are <strong>not</strong> deleted — they stay in the register but become
                    unowned. Consider deactivating the person instead to keep the history intact.
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setCheck(null)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
                Delete {check.found}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

/** Header cell checkbox for "select all in this list". */
export function SelectAllHeader({
  ids,
  selected,
  onToggleAll,
  className,
}: {
  ids: Id[]
  selected: Set<Id>
  onToggleAll: (ids: Id[]) => void
  className?: string
}) {
  const all = ids.length > 0 && ids.every((id) => selected.has(id))
  const some = ids.some((id) => selected.has(id))
  return (
    <span className={cn('inline-flex', className)}>
      <SelectCheckbox checked={all} indeterminate={some} onChange={() => onToggleAll(ids)} label="Select all" />
    </span>
  )
}
