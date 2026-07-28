import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api, type RiskChain } from '../api'
import { Badge, Card, EmptyState } from './ui'

function registerHref(itemType: string, itemId: number): string | null {
  if (itemType === 'action' || itemType === 'commitment') return `/register?open=${itemType}-${itemId}`
  if (itemType === 'topic') return '/topics'
  return null
}

function ItemRef({ type, id, title, className }: { type: string; id: number; title: string; className?: string }) {
  const href = registerHref(type, id)
  if (!href) return <span className={className}>{title}</span>
  return (
    <Link to={href} className={`${className ?? ''} underline decoration-dotted underline-offset-2 hover:text-indigo-600 dark:hover:text-indigo-400`}>
      {title}
    </Link>
  )
}

export function RiskChainsCard({ className }: { className?: string }) {
  const { data: risks = [] } = useQuery({
    queryKey: ['risks'],
    queryFn: () => api.get<RiskChain[]>('/planner/risks'),
  })

  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          <AlertTriangle size={14} className="text-amber-500" /> Dependency risk chains
        </span>
      }
      className={className}
    >
      {risks.length === 0 ? (
        <EmptyState
          title="No downstream risk detected"
          hint="Link items with blocks/precedes and Fulcrum flags everything downstream of anything late, blocked, or at risk."
        />
      ) : (
        <div className="space-y-2">
          {risks.map((risk, index) => (
            <div
              key={index}
              className="rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2 text-xs dark:border-amber-900/60 dark:bg-amber-950/20"
            >
              <ItemRef type={risk.item_type} id={risk.item_id} title={risk.item_title} className="font-semibold" />
              <span className="text-slate-500"> ({risk.item_type.replace('_', ' ')}) is exposed — </span>
              <ItemRef
                type={risk.cause_type}
                id={risk.cause_id}
                title={risk.cause_title}
                className="font-medium text-amber-700 dark:text-amber-400"
              />
              <span className="text-slate-500"> is {risk.cause_reason}</span>
              {risk.chain_length > 1 && (
                <Badge tone="amber" className="ml-1.5">
                  {risk.chain_length} steps up the chain
                </Badge>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
