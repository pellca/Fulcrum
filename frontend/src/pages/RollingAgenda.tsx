import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, FileDown } from 'lucide-react'
import { api } from '../api'
import {
  Badge,
  Button,
  Card,
  CapacityBar,
  EmptyState,
  IntentBadge,
  PageHeader,
  SegmentedControl,
  Select,
  Spinner,
  cn,
  dueTone,
  fmtDate,
  intentSolid,
  peopleLabel,
} from '../components/ui'

interface PersonMini {
  id: number
  name: string
}

interface RollingTopic {
  id: number
  title: string
  intent: string
  duration_minutes: number
  readiness: string
  status: string
  recurring: boolean
  target_by: string | null
  papers_url: string | null
  sponsors: PersonMini[]
}

interface RollingCell {
  agenda_item_id: number
  meeting_id: number
  sequence: number
  allocated_minutes: number
  outcome_note: string | null
}

interface RollingMeeting {
  id: number
  scheduled_at: string
  status: string
  diary_event_id: string | null
  needs_review: boolean
  location: string | null
  allocated_minutes: number
  capacity_minutes: number
  item_count: number
}

interface RollingRow {
  topic: RollingTopic
  cells: (RollingCell | null)[]
}

interface RollingBand {
  workstream: { id: number; name: string; colour: string } | null
  label: string
  category: string | null
  rows: RollingRow[]
}

interface RollingAgendaOut {
  forum: { id: number; name: string; cadence: string | null; capacity_minutes: number; colour: string }
  meetings: RollingMeeting[]
  bands: RollingBand[]
}

type ViewMode = 'columns' | 'grid'

const VIEW_KEY = 'fulcrum-rolling-agenda-view'

/** Landscape only while this page prints — @page cannot be scoped by a selector,
 *  so the rule is injected for the duration of the print and removed after.
 *
 *  `window.print()` blocks until the dialog closes in Chrome/Edge, but
 *  returns immediately in Safari/webviews before the page finishes
 *  serialising — cleaning up in a `finally` right after the call strips the
 *  `@page` rule mid-render there. Do the real cleanup from `afterprint`,
 *  which fires once printing has actually finished; fall back to an
 *  immediate synchronous cleanup only when the browser doesn't support that
 *  event at all, so Chrome/Edge still behave exactly as before. */
function printLandscape(title: string) {
  document.getElementById('rolling-agenda-page')?.remove()
  const style = document.createElement('style')
  style.id = 'rolling-agenda-page'
  style.textContent = '@page { size: A4 landscape; margin: 10mm; }'
  const originalTitle = document.title
  document.head.appendChild(style)
  document.body.classList.add('print-landscape')
  document.title = title

  let cleaned = false
  const cleanup = () => {
    if (cleaned) return
    cleaned = true
    window.removeEventListener('afterprint', cleanup)
    document.title = originalTitle
    document.body.classList.remove('print-landscape')
    document.getElementById('rolling-agenda-page')?.remove()
  }
  window.addEventListener('afterprint', cleanup)

  try {
    window.print()
    if (!('onafterprint' in window)) cleanup()
  } catch (err) {
    cleanup()
    throw err
  }
}

/** Split a band into the two shapes the table renders.
 *
 *  A topic that occupies several columns needs a name in the left-hand column:
 *  that single label is what ties its chips together across the dates, and it is
 *  the part of the matrix that has always worked. A topic that occupies exactly
 *  one column does not — spending a whole row on one chip is what turns a
 *  12-month window into a sparse diagonal, so those get their name inside the
 *  cell instead.
 *
 *  `recurring` is included on the standing side so a standing item that happens
 *  to land on only one meeting in this particular window still reads as standing.
 */
function splitBand(rows: RollingRow[]) {
  const standing: RollingRow[] = []
  const oneOff: RollingRow[] = []
  for (const row of rows) {
    const filled = row.cells.filter(Boolean).length
    ;(filled > 1 || row.topic.recurring ? standing : oneOff).push(row)
  }
  return { standing, oneOff }
}

/** Pack one-off rows into columns. Every one of them spans exactly one column,
 *  so this is a transpose rather than an interval packing: each column stacks its
 *  own topics in agenda order, and the band needs as many table rows as the
 *  busiest column has cards.
 *
 *  Returned as rows-of-columns (not columns-of-rows) because one `<tr>` per stack
 *  index is what lets a long band paginate — `break-inside: avoid` on `tr` would
 *  make a single tall row taller than the page it has to print on. */
function packColumns(rows: RollingRow[], columnCount: number): (RollingRow | null)[][] {
  const stacks: RollingRow[][] = Array.from({ length: columnCount }, () => [])
  for (const row of rows) {
    const index = row.cells.findIndex(Boolean)
    if (index >= 0) stacks[index].push(row)
  }
  for (const stack of stacks) {
    stack.sort((a, b) => (a.cells.find(Boolean)?.sequence ?? 0) - (b.cells.find(Boolean)?.sequence ?? 0))
  }
  const depth = Math.max(0, ...stacks.map((stack) => stack.length))
  return Array.from({ length: depth }, (_, level) => stacks.map((stack) => stack[level] ?? null))
}

export default function RollingAgenda() {
  const { id } = useParams()
  const [limit, setLimit] = useState(8)
  const [includePast, setIncludePast] = useState(false)
  const [view, setView] = useState<ViewMode>(
    () => (localStorage.getItem(VIEW_KEY) as ViewMode) ?? 'columns',
  )

  const setViewMode = (mode: ViewMode) => {
    localStorage.setItem(VIEW_KEY, mode)
    setView(mode)
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['rolling-agenda', id, limit, includePast],
    queryFn: () =>
      api.get<RollingAgendaOut>(
        `/forums/${id}/rolling-agenda?limit=${limit}&include_past=${includePast}`,
      ),
  })

  if (isLoading) return <Spinner />
  if (isError || !data)
    return (
      <div>
        <BackLink />
        <EmptyState title="Forum not found" hint="It may have been deleted. Pick another from the meetings page." />
      </div>
    )

  const { forum, meetings, bands } = data
  const columns = meetings.length
  const topicCount = bands.reduce((sum, band) => sum + band.rows.length, 0)

  // In grid mode nothing is packed — every row keeps its left-hand label, which
  // is the view this page shipped with.
  const split = bands.map((band) =>
    view === 'grid' ? { standing: band.rows, oneOff: [] } : splitBand(band.rows),
  )
  // With nothing standing there is no label to show, so the topic column is dead
  // width — drop it and give the space back to the dates.
  const showTopicCol = split.some((band) => band.standing.length > 0)
  const span = columns + (showTopicCol ? 1 : 0)

  return (
    <div className="dashboard-print">
      <div className="no-print">
        <BackLink />
      </div>

      <PageHeader
        title={`${forum.name} — rolling agenda`}
        subtitle={
          columns
            ? `${columns} meeting${columns === 1 ? '' : 's'} · ${topicCount} topic${topicCount === 1 ? '' : 's'} · ${forum.cadence ?? 'no cadence set'}`
            : forum.cadence ?? undefined
        }
        actions={
          <div className="no-print flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <input
                type="checkbox"
                className="rounded border-slate-300"
                checked={includePast}
                onChange={(e) => setIncludePast(e.target.checked)}
              />
              Show past
            </label>
            <SegmentedControl<ViewMode>
              value={view}
              onChange={setViewMode}
              options={[
                { value: 'columns', label: 'Columns', title: 'One-off topics named inside their own meeting column' },
                { value: 'grid', label: 'Grid', title: 'Every topic on its own row, named in the left column' },
              ]}
            />
            <Select value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))} className="!w-24">
              <option value="4">4 dates</option>
              <option value="8">8 dates</option>
              <option value="12">12 dates</option>
              <option value="24">24 dates</option>
            </Select>
            <Button
              variant="secondary"
              onClick={() => printLandscape(`${forum.name} rolling agenda ${fmtDate(new Date().toISOString())}`)}
            >
              <FileDown size={15} /> Print / PDF
            </Button>
          </div>
        }
      />

      {!columns ? (
        <EmptyState
          title="No meetings in this window"
          hint={
            includePast
              ? 'This forum has no meetings scheduled at all — add one from the meetings page.'
              : 'Every meeting for this forum is in the past. Tick "Show past" to see them.'
          }
        />
      ) : (
        <Card className="overflow-x-auto">
          <table className={cn('w-full text-left text-xs', view === 'grid' ? 'min-w-[720px]' : 'min-w-[840px]')}>
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                {showTopicCol && (
                  <th className="sticky left-0 z-10 w-40 bg-white py-2 pr-3 align-bottom font-medium text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                    Topic
                  </th>
                )}
                {meetings.map((meeting) => (
                  <th
                    key={meeting.id}
                    className={cn('px-1 py-2 align-bottom font-medium', view === 'grid' ? 'min-w-28' : 'min-w-[9.5rem]')}
                  >
                    <Link to={`/meetings/${meeting.id}`} className="block hover:text-indigo-600 dark:hover:text-indigo-400">
                      <span className="flex items-center gap-1 font-semibold text-slate-800 dark:text-slate-100">
                        {fmtDate(meeting.scheduled_at)}
                        {meeting.status !== 'planned' && (
                          <span
                            className={cn(
                              'h-1.5 w-1.5 rounded-full',
                              meeting.status === 'held'
                                ? 'bg-emerald-500'
                                : meeting.status === 'cancelled'
                                  ? 'bg-rose-500'
                                  : 'bg-sky-500',
                            )}
                            title={meeting.status}
                          />
                        )}
                        {meeting.needs_review && (
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" title="Diary moved — check the time" />
                        )}
                      </span>
                      <span
                        className="block max-w-36 truncate text-[11px] font-normal text-slate-500 dark:text-slate-400"
                        title={meeting.location ?? undefined}
                      >
                        {meeting.scheduled_at.slice(11, 16)}
                        {meeting.location ? ` · ${meeting.location}` : ''}
                      </span>
                      <CapacityBar
                        allocated={meeting.allocated_minutes}
                        capacity={meeting.capacity_minutes}
                        size="sm"
                        className="mt-1"
                      />
                      <span
                        className={cn(
                          'block text-[10px] font-normal',
                          meeting.allocated_minutes > meeting.capacity_minutes ? 'text-rose-500' : 'text-slate-400',
                        )}
                      >
                        {meeting.allocated_minutes}/{meeting.capacity_minutes} min
                      </span>
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>

            {bands.length === 0 ? (
              <tbody>
                <tr>
                  <td colSpan={span} className="py-6">
                    <EmptyState
                      title="Nothing on any agenda yet"
                      hint="Open a meeting and add topics — its ranked candidates are already waiting there."
                    />
                  </td>
                </tr>
              </tbody>
            ) : (
              bands.map((band, bandIndex) => {
                const { standing, oneOff } = split[bandIndex]
                const packed = packColumns(oneOff, columns)
                return (
                  <tbody key={band.workstream?.id ?? 'unassigned'}>
                    <tr>
                      <td
                        colSpan={span}
                        className="bg-slate-50 px-1 py-1 text-[11px] font-semibold tracking-wide text-slate-500 uppercase dark:bg-slate-800/60 dark:text-slate-400"
                      >
                        <span className="flex items-center gap-1.5">
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ background: band.workstream?.colour ?? '#94a3b8' }}
                          />
                          {band.label}
                          <span className="font-normal text-slate-400">· {band.rows.length}</span>
                        </span>
                      </td>
                    </tr>

                    {standing.map((row) => (
                      <tr key={row.topic.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                        {showTopicCol && (
                          <td className="sticky left-0 z-10 w-40 bg-white py-1.5 pr-3 align-top dark:bg-slate-900">
                            <Link
                              to={`/topics?open=${row.topic.id}`}
                              className="block truncate text-[13px] font-medium hover:text-indigo-600 dark:hover:text-indigo-400"
                              title={row.topic.title}
                            >
                              {row.topic.title}
                            </Link>
                            <span className="mt-0.5 flex flex-wrap items-center gap-1">
                              <IntentBadge intent={row.topic.intent} />
                              <Badge tone="slate">{row.topic.duration_minutes}m</Badge>
                              {row.topic.recurring && <Badge tone="amber">standing</Badge>}
                              {row.topic.target_by && (
                                <Badge tone={dueTone(row.topic.target_by)}>by {fmtDate(row.topic.target_by)}</Badge>
                              )}
                              {row.topic.papers_url && (
                                <a
                                  href={row.topic.papers_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-slate-400 hover:text-indigo-600"
                                  title="Papers"
                                >
                                  <ExternalLink size={12} />
                                </a>
                              )}
                              {row.topic.sponsors.length > 0 && (
                                <span
                                  className="text-[11px] text-slate-400"
                                  title={peopleLabel(row.topic.sponsors)}
                                >
                                  {peopleLabel(row.topic.sponsors, 1)}
                                </span>
                              )}
                            </span>
                          </td>
                        )}
                        {meetings.map((meeting, index) => {
                          const cell = row.cells[index] ?? null
                          return (
                            <td key={meeting.id} className="px-1 py-1.5 align-middle">
                              <Link to={`/meetings/${meeting.id}`} className="block">
                                {cell ? (
                                  <span
                                    className={cn(
                                      'agenda-chip flex h-7 items-center justify-center rounded-md text-[11px] font-semibold',
                                      cell.outcome_note
                                        ? 'border border-slate-300 bg-white text-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-400'
                                        : (intentSolid[row.topic.intent] ?? intentSolid.slate),
                                      !cell.outcome_note &&
                                        cell.allocated_minutes !== row.topic.duration_minutes &&
                                        'ring-2 ring-slate-400 ring-offset-1 dark:ring-offset-slate-900',
                                    )}
                                    title={[
                                      `#${cell.sequence} · ${row.topic.title}`,
                                      `${cell.allocated_minutes} min allocated`,
                                      cell.outcome_note ? `Outcome: ${cell.outcome_note}` : null,
                                    ]
                                      .filter(Boolean)
                                      .join('\n')}
                                  >
                                    {cell.outcome_note ? '✓ ' : ''}
                                    {cell.allocated_minutes}
                                  </span>
                                ) : (
                                  <span className="block h-7 rounded-md bg-slate-50 dark:bg-slate-800/40" />
                                )}
                              </Link>
                            </td>
                          )
                        })}
                      </tr>
                    ))}

                    {packed.map((level, levelIndex) => (
                      <tr
                        key={`packed-${levelIndex}`}
                        className="border-b border-slate-100 last:border-0 dark:border-slate-800/60"
                      >
                        {showTopicCol && (
                          <td className="sticky left-0 z-10 w-40 bg-white dark:bg-slate-900" />
                        )}
                        {meetings.map((meeting, index) => (
                          <td key={meeting.id} className="px-1 py-1 align-top">
                            {level[index] && <TopicCard row={level[index]!} meetingIndex={index} />}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                )
              })
            )}

            {bands.length > 0 && (
              <tfoot>
                <tr className="border-t border-slate-200 dark:border-slate-800">
                  {showTopicCol && (
                    <td className="sticky left-0 z-10 w-40 bg-white py-1.5 pr-3 text-[11px] font-medium text-slate-400 dark:bg-slate-900">
                      Total
                    </td>
                  )}
                  {meetings.map((meeting) => (
                    <td key={meeting.id} className="px-1 py-1.5 text-[10px] whitespace-nowrap text-slate-400">
                      {meeting.allocated_minutes}/{meeting.capacity_minutes} min · {meeting.item_count} item
                      {meeting.item_count === 1 ? '' : 's'}
                    </td>
                  ))}
                </tr>
              </tfoot>
            )}
          </table>

          <p className="mt-2 text-[11px] text-slate-400">
            {view === 'columns'
              ? 'A named card is a topic on one date; a row of chips is a standing item running across dates. '
              : ''}
            Colour is the topic's intent · a ringed cell is re-timed from its default duration · ✓ means an outcome
            was recorded · click anything to open that meeting. More than ~
            {view === 'columns' ? '7' : '10'} columns will spill across pages — drop the count for a clean print.
          </p>
        </Card>
      )}
    </div>
  )
}

/** A one-off topic, named inside the column of the meeting it belongs to. Carries
 *  the same two states as the chips it replaces: muted with a ✓ once an outcome is
 *  recorded, ringed when the allocation differs from the topic's own duration. */
function TopicCard({ row, meetingIndex }: { row: RollingRow; meetingIndex: number }) {
  const cell = row.cells[meetingIndex]!
  const { topic } = row
  const done = Boolean(cell.outcome_note)
  const retimed = !done && cell.allocated_minutes !== topic.duration_minutes

  return (
    <Link to={`/meetings/${cell.meeting_id}`} className="block">
      <div
        className={cn(
          'agenda-card flex gap-1.5 overflow-hidden rounded-md border pr-1.5 transition-colors',
          done
            ? 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/40'
            : 'border-slate-200 bg-white hover:border-indigo-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-700',
          retimed && 'ring-2 ring-slate-400 ring-offset-1 dark:ring-offset-slate-900',
        )}
        title={[
          `#${cell.sequence} · ${topic.title}`,
          `${cell.allocated_minutes} min allocated`,
          topic.sponsors.length ? `Sponsor: ${peopleLabel(topic.sponsors)}` : null,
          cell.outcome_note ? `Outcome: ${cell.outcome_note}` : null,
        ]
          .filter(Boolean)
          .join('\n')}
      >
        <span
          className={cn('w-1 shrink-0', done ? 'bg-slate-300 dark:bg-slate-600' : (intentSolid[topic.intent] ?? intentSolid.slate))}
        />
        <div className="min-w-0 py-1">
          <span
            className={cn(
              'block text-[11px] leading-snug font-semibold line-clamp-2',
              done ? 'text-slate-500 dark:text-slate-400' : 'text-slate-800 dark:text-slate-100',
            )}
          >
            {done ? '✓ ' : ''}
            {topic.title}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-slate-400">
            <span className="tabular-nums">#{cell.sequence}</span>
            <span className="font-medium text-slate-500 dark:text-slate-400">{cell.allocated_minutes}m</span>
            <span>{topic.intent}</span>
            {topic.target_by && (
              <Badge tone={dueTone(topic.target_by)} className="px-1.5 py-0 text-[10px]">
                by {fmtDate(topic.target_by)}
              </Badge>
            )}
            {topic.papers_url && (
              <a
                href={topic.papers_url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-slate-400 hover:text-indigo-600"
                title="Papers"
              >
                <ExternalLink size={11} />
              </a>
            )}
            {topic.sponsors.length > 0 && <span className="truncate">{peopleLabel(topic.sponsors, 1)}</span>}
          </span>
        </div>
      </div>
    </Link>
  )
}

function BackLink() {
  return (
    <Link
      to="/meetings"
      className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-indigo-600"
    >
      <ArrowLeft size={13} /> Meetings
    </Link>
  )
}
