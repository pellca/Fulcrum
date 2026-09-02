export const BASE = '/api'

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
  pin_discussion: boolean
  notes: string | null
  aliases: { id: number; alias: string }[]
}

export type PersonNoteKind = 'feedback' | 'call' | 'observation' | 'general'

export interface PersonNote {
  id: number
  person_id: number
  kind: PersonNoteKind
  note: string
  noted_on: string
  discussed_on: string | null
  source: 'manual' | 'mail' | 'meeting'
}

export function listPersonNotes(personId: number, params?: { kind?: string; undiscussed?: boolean }) {
  const search = new URLSearchParams()
  if (params?.kind) search.set('kind', params.kind)
  if (params?.undiscussed) search.set('undiscussed', 'true')
  const qs = search.toString()
  return api.get<PersonNote[]>(`/people/${personId}/notes${qs ? `?${qs}` : ''}`)
}

export function createPersonNote(personId: number, body: { kind: PersonNoteKind; note: string; noted_on?: string }) {
  return api.post<PersonNote>(`/people/${personId}/notes`, body)
}

export type PersonNotePatch = Partial<Pick<PersonNote, 'kind' | 'note' | 'noted_on' | 'discussed_on'>>

export function updatePersonNote(noteId: number, body: PersonNotePatch) {
  return api.patch<PersonNote>(`/people/notes/${noteId}`, body)
}

export function deletePersonNote(noteId: number) {
  return api.delete(`/people/notes/${noteId}`)
}

export function markNotesDiscussed(personId: number, ids?: number[]) {
  return api.post<{ marked: number }>(`/people/${personId}/notes/mark-discussed`, ids ? { ids } : undefined)
}

// ---------- discussion points ----------

export interface DiscussionLink {
  type: string
  id: number
  title: string
}

export interface DiscussionPoint {
  id: number
  person_id: number
  title: string
  detail: string | null
  priority: string
  status: 'open' | 'closed'
  raised_on: string
  last_discussed_on: string | null
  times_discussed: number
  closed_on: string | null
  outcome: string | null
  links: DiscussionLink[]
}

export function listDiscussionPoints(personId: number, includeClosed = false) {
  const search = new URLSearchParams({ person_id: String(personId) })
  if (includeClosed) search.set('include_closed', 'true')
  return api.get<DiscussionPoint[]>(`/discussion-points?${search.toString()}`)
}

export function createDiscussionPoint(body: {
  person_id: number
  title: string
  detail?: string | null
  priority?: string
  link_to?: { type: string; id: number }
}) {
  return api.post<DiscussionPoint>('/discussion-points', body)
}

export function updateDiscussionPoint(
  id: number,
  body: Partial<Pick<DiscussionPoint, 'title' | 'detail' | 'priority' | 'status' | 'outcome'>>,
) {
  return api.patch<DiscussionPoint>(`/discussion-points/${id}`, body)
}

export function markDiscussionPointDiscussed(id: number) {
  return api.post<DiscussionPoint>(`/discussion-points/${id}/discussed`)
}

export function deleteDiscussionPoint(id: number) {
  return api.delete(`/discussion-points/${id}`)
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
  sort_order: number
  owners: PersonMini[]
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
  recurring: boolean
  target_by: string | null
  papers_url: string | null
  sponsors: PersonMini[]
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
    recurring: boolean
    sponsors: PersonMini[]
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
  discussion: { person: PersonMini; points: DiscussionPoint[] } | null
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
  diary_imported: boolean
  key_dates: {
    id: number
    title: string
    date: string
    kind: string
    hard: boolean
    days_away: number
    workstream: string | null
  }[]
  diary: {
    id: string
    subject: string | null
    start_time: string | null
    end_time: string | null
    is_all_day: boolean
    location: string | null
    organizer: string | null
    span_day: number
    span_days: number
    meeting: {
      id: number
      forum: string
      colour: string
      status: string
      needs_review: boolean
      agenda_count: number
      allocated_minutes: number
      capacity_minutes: number
    } | null
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

export interface MailRecipient {
  name: string | null
  email: string | null
}

export type MailFolder = 'inbox' | 'sent'
export type MailTriage = 'pending' | 'linked' | 'dismissed'

export interface MailMessage {
  id: number
  message_id: string
  conversation_id: string | null
  folder: MailFolder
  subject: string | null
  sender_name: string | null
  sender_email: string | null
  to_recipients: MailRecipient[]
  cc_recipients: MailRecipient[]
  sent_at: string | null
  received_at: string | null
  occurred_date: string
  body_text: string | null
  has_attachments: boolean
  triage: MailTriage
  triaged_at: string | null
  sender_person: PersonMini | null
  matched_people: { id: number; name: string; email: string | null; matched_email: string }[]
}

export interface MailStats {
  pending: number
  linked: number
  dismissed: number
  total: number
}

export interface MailImportSummary {
  added: number
  updated: number
  purged: number
}

export function listMailMessages(params: { days: number; folder?: MailFolder; triage?: MailTriage }) {
  const search = new URLSearchParams()
  search.set('days', String(params.days))
  if (params.folder) search.set('folder', params.folder)
  if (params.triage) search.set('triage', params.triage)
  return api.get<MailMessage[]>(`/mail/messages?${search.toString()}`)
}

export function importMailPath(path: string) {
  return api.post<MailImportSummary>('/mail/import', { path })
}

export function importMailUpload(file: File) {
  return api.upload<MailImportSummary>('/mail/import-upload', file)
}

export function mailStats() {
  return api.get<MailStats>('/mail/stats')
}

// ---------- mail triage action rail ----------

export type MailSuggestionType = 'action' | 'commitment'

export interface MailSuggestion {
  type: MailSuggestionType
  id: number
  title: string
  status: string
  due_date: string | null
  owner: PersonMini | null
  score: number
  reasons: string[]
}

export function mailSuggestions(messageId: number) {
  return api.get<{ suggestions: MailSuggestion[] }>(`/mail/${messageId}/suggestions`)
}

export interface MailLogChaseResult {
  chase_id: number
  target_type: MailSuggestionType
  target_id: number
}

export function mailLogChase(
  messageId: number,
  body: { target_type: MailSuggestionType; target_id: number; note?: string | null; next_chase_on?: string | null },
) {
  return api.post<MailLogChaseResult>(`/mail/${messageId}/log-chase`, body)
}

export interface MailCreateActionResult {
  action_id: number
  title: string
  owner_name: string | null
  due_date: string | null
  warnings: string[]
}

export function mailCreateAction(messageId: number, text: string) {
  return api.post<MailCreateActionResult>(`/mail/${messageId}/create-action`, { text })
}

export interface MailCloseActionResult {
  action_id: number
  status: string
}

export function mailCloseAction(messageId: number, actionId: number) {
  return api.post<MailCloseActionResult>(`/mail/${messageId}/close-action`, { action_id: actionId })
}

export function mailPersonNote(messageId: number, body: { person_id: number; kind?: PersonNoteKind; note: string }) {
  return api.post<PersonNote>(`/mail/${messageId}/person-note`, body)
}

export function mailDismiss(messageId: number) {
  return api.post<{ triage: MailTriage }>(`/mail/${messageId}/dismiss`)
}

export function mailReopen(messageId: number) {
  return api.post<{ triage: MailTriage }>(`/mail/${messageId}/reopen`)
}

export function getMailMessage(messageId: number) {
  return api.get<MailMessage>(`/mail/messages/${messageId}`)
}

// ---------- register: search-all-open-items picker + export ----------

export interface RegisterPickerItem {
  type: MailSuggestionType
  id: number
  title: string
  status: string
  due_date: string | null
  owner: PersonMini | null
}

export function registerPicker(q: string) {
  const search = new URLSearchParams()
  search.set('q', q)
  return api.get<{ items: RegisterPickerItem[] }>(`/register/picker?${search.toString()}`)
}

export function registerExportUrl(params: { format: 'csv' | 'xlsx'; chases: boolean; links: boolean }) {
  const search = new URLSearchParams()
  search.set('format', params.format)
  search.set('chases', String(params.chases))
  search.set('links', String(params.links))
  return `${BASE}/register/export?${search.toString()}`
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
    diary_imported: boolean
  key_dates: { id: number; title: string; date: string; kind: string; hard: boolean }[]
  }[]
  meetings: { id: number; forum: string; colour: string; scheduled_at: string; status: string }[]
}
