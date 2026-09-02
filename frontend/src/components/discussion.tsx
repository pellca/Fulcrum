// Shared discussion-point row: Today's pinned-person card and the 1:1 pack
// render the exact same list (backend/app/services/discussion.py is the one
// place the ordering and shape are decided), so the row itself lives here
// once rather than being copied between the two pages.
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { markDiscussionPointDiscussed, updateDiscussionPoint, type DiscussionPoint } from '../api'
import { Badge, Button, priorityTone } from './ui'
import { entityRoute } from './entityRoutes'

function staleness(point: DiscussionPoint): string {
  if (!point.last_discussed_on) return 'not yet raised'
  const days = Math.floor((Date.now() - new Date(point.last_discussed_on).getTime()) / 86400000)
  if (days <= 0) return 'discussed today'
  if (days === 1) return 'last discussed yesterday'
  return `last discussed ${days}d ago`
}

export function DiscussionPointRow({ point, onChanged }: { point: DiscussionPoint; onChanged: () => void }) {
  const navigate = useNavigate()
  const discussed = useMutation({
    mutationFn: () => markDiscussionPointDiscussed(point.id),
    onSuccess: () => {
      toast.success('Marked discussed')
      onChanged()
    },
  })
  const close = useMutation({
    mutationFn: () => updateDiscussionPoint(point.id, { status: 'closed' }),
    onSuccess: () => {
      toast.success('Closed')
      onChanged()
    },
  })

  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium">{point.title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span>{staleness(point)}</span>
          {point.links.map((link) => {
            const route = entityRoute(link.type, link.id)
            return route ? (
              <button
                key={`${link.type}-${link.id}`}
                onClick={() => navigate(route)}
                className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-indigo-600 hover:underline dark:bg-slate-800 dark:text-indigo-400"
              >
                {link.title}
              </button>
            ) : (
              <span key={`${link.type}-${link.id}`} className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
                {link.title}
              </span>
            )
          })}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Badge tone={priorityTone[point.priority]}>{point.priority}</Badge>
        <div className="no-print flex items-center gap-1.5">
          <Button size="sm" variant="secondary" onClick={() => discussed.mutate()} disabled={discussed.isPending}>
            Discussed
          </Button>
          <Button size="sm" variant="secondary" onClick={() => close.mutate()} disabled={close.isPending}>
            Close
          </Button>
        </div>
      </div>
    </div>
  )
}
