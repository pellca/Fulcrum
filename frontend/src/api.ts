const BASE = '/api'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: 'DELETE' }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<T>(path, { method: 'POST', body: form })
  },
}

// ---------- types ----------

export interface PersonMini {
  id: number
  name: string
}

export interface Person extends PersonMini {
  email: string | null
  team: string | null
  role: string | null
  is_bpm: boolean
  active: boolean
  notes: string | null
  aliases: { id: number; alias: string }[]
}

export interface WorkstreamMini {
  id: number
  name: string
  colour: string
}

export interface Workstream extends WorkstreamMini {
  description: string | null
  category: string
  status: string
  owner: PersonMini | null
}

export interface Commitment {
  id: number
  title: string
  description: string | null
  origin: string
  origin_detail: string | null
  due_date: string | null
  status: string
  priority: string
  owner: PersonMini | null
  workstream: WorkstreamMini | null
  created_at: string
  action_count: number
  next_chase_on: string | null
}

export interface Action {
  id: number
  title: string
  description: string | null
  due_date: string | null
  status: string
  priority: string
  notes: string | null
  owner: PersonMini | null
  commitment: { id: number; title: string } | null
  workstream: WorkstreamMini | null
  created_at: string
  next_chase_on: string | null
}

export interface Chase {
  id: number
  action_id: number | null
  commitment_id: number | null
  chased_on: string
  method: string
  note: string | null
  next_chase_on: string | null
}

export interface LinkItem {
  id: number
  from_type: string
  from_id: number
  to_type: string
  to_id: number
  kind: string
  rationale: string | null
  from_title: string
  to_title: string
}

export interface Forum {
  id: number
  name: string
  cadence: string | null
  capacity_minutes: number
  audience: string | null
  colour: string
  chair: PersonMini | null
}

export interface Topic {
  id: number
  title: string
  description: string | null
  intent: string
  duration_minutes: number
  readiness: string
  status: string
  target_by: string | null
  papers_url: string | null
  sponsor: PersonMini | null
  workstream: WorkstreamMini | null
  commitment: { id: number; title: string } | null
  created_at: string
}

export interface AgendaItem {
  id: number
  topic_id: number
  sequence: number
  allocated_minutes: number
  outcome_note: string | null
  topic: {
    id: number
    title: string
    intent: string
    duration_minutes: number
    readiness: string
    sponsor: PersonMini | null
    workstream: WorkstreamMini | null
  }
}

export interface Meeting {
  id: number
  forum_id: number
  scheduled_at: string
  status: string
  diary_event_id: string | null
  needs_review: boolean
  notes: string | null
  forum: Forum
  agenda_items: AgendaItem[]
}

export interface ScoredTopic {
  topic: Topic
  score: number
  reasons: string[]
}

export interface Decision {
  id: number
  meeting_id: number | null
  title: string
  detail: string | null
  decided_on: string | null
  status: string
  owner: PersonMini | null
  created_at: string
}

export interface KeyDate {
  id: number
  title: string
  date: string
  kind: string
  hard: boolean
  notes: string | null
  workstream: WorkstreamMini | null
}

export interface DiaryEvent {
  id: string
  subject: string | null
  start: string | null
  end: string | null
  start_date: string | null
  start_time: string | null
  end_date: string | null
  end_time: string | null
  organizer: string | null
  required_attendees: string[]
  optional_attendees: string[]
  location: string | null
  categories: string[]
  is_recurring: boolean
  is_all_day: boolean
  status: string
  cancelled_at: string | null
  moved_to_event_id: string | null
}

export interface ModuleManifest {
  name: string
  label?: string
  description?: string
  platform: string
  available: boolean
  error?: string
  args: { name: string; label?: string; required?: boolean; default?: string }[]
}

export interface ModuleRun {
  id: number
  module_name: string
  started_at: string | null
  finished_at: string | null
  status: string
  args: string | null
  log: string
  artifact_path: string | null
}

export interface DashboardSummary {
  today: string
  decisions_for_review: {
    id: number
    title: string
    status: string
    owner: string | null
    decided_on: string | null
    review_on: string | null
    days_overdue: number
  }[]
  overdue_actions: DashItem[]
  due_soon_actions: DashItem[]
  overdue_commitments: DashItem[]
  due_soon_commitments: DashItem[]
  chase_queue: ChaseQueueItem[]
  decision_ready: {
    id: number
    title: string
    sponsor: string | null
    target_by: string | null
    duration_minutes: number
  }[]
  key_dates: {
    id: number
    title: string
    date: string
    kind: string
    hard: boolean
    days_away: number
    workstream: string | null
  }[]
  meetings: {
    id: number
    forum: string
    colour: string
    scheduled_at: string
    status: string
    needs_review: boolean
    agenda_count: number
    allocated_minutes: number
    capacity_minutes: number
  }[]
}

export interface DashItem {
  id: number
  title: string
  owner: string | null
  due_date: string | null
  status: string
  priority: string
  origin?: string
  workstream: string | null
}

export interface ChaseQueueItem {
  item_type: string
  item_id: number
  title: string
  owner_name: string | null
  due_date: string | null
  last_chased_on: string
  next_chase_on: string
  days_overdue_chase: number
}

export interface RiskChain {
  item_type: string
  item_id: number
  item_title: string
  cause_type: string
  cause_id: number
  cause_title: string
  cause_reason: string
  chain_length: number
}

export interface TimelineData {
  from: string
  to: string
  lanes: {
    workstream: { id: number; name: string; colour: string; category: string } | null
    commitments: {
      id: number
      title: string
      due_date: string
      status: string
      priority: string
      owner: string | null
    }[]
    key_dates: { id: number; title: string; date: string; kind: string; hard: boolean }[]
  }[]
  meetings: { id: number; forum: string; colour: string; scheduled_at: string; status: string }[]
}
