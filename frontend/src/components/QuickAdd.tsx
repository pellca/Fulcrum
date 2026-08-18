import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Zap } from 'lucide-react'
import { api } from '../api'
import { Select } from './ui'

const placeholders: Record<'action' | 'commitment' | 'topic' | 'note', string> = {
  action: 'Quick add…  e.g. Chase scope pack @sarah #credit due:fri !high   (Ctrl+K)',
  commitment: 'Quick add…  e.g. Chase scope pack @sarah #credit due:fri !high origin:principal   (Ctrl+K)',
  topic: 'Quick add…  e.g. Chase scope pack @sarah #credit due:fri   (Ctrl+K)',
  note: 'Quick add…  e.g. Handled the escalation well @sarah kind:feedback   (Ctrl+K)',
}

export function QuickAdd() {
  const [text, setText] = useState('')
  const [type, setType] = useState<'action' | 'commitment' | 'topic' | 'note'>('action')
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const mutation = useMutation({
    mutationFn: () => api.post<{ id: number; title: string; warnings: string[] }>('/quickadd', { text, type }),
    onSuccess: (res) => {
      toast.success(`${type} added: ${res.title}`, {
        description: res.warnings.length ? res.warnings.join('; ') : undefined,
      })
      setText('')
      queryClient.invalidateQueries()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  return (
    <form
      className="flex w-full max-w-xl items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (text.trim()) mutation.mutate()
      }}
    >
      <div className="relative flex-1">
        <Zap size={14} className="absolute top-1/2 left-3 -translate-y-1/2 text-indigo-500" />
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholders[type]}
          title={type === 'note' ? 'Needs an @person. Optional kind:feedback|call|observation|general (defaults to general).' : undefined}
          className="w-full rounded-lg border border-slate-300 bg-slate-50 py-1.5 pr-3 pl-8 text-[13px] placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:focus:bg-slate-900"
        />
      </div>
      <Select
        value={type}
        onChange={(e) => setType(e.target.value as typeof type)}
        className="!w-auto !py-1.5 text-[13px]"
      >
        <option value="action">Action</option>
        <option value="commitment">Commitment</option>
        <option value="topic">Topic</option>
        <option value="note">Note</option>
      </Select>
    </form>
  )
}
