# Fulcrum

**Chief of Staff operating platform** — a local, browser-based tool that links commitments,
actions, meeting agendas and forward planning into one system, built for the Chief of Staff of an
Internal Audit & Investigations function.

> *The leverage point: small, well-placed effort moving heavy things.*

## What it does

| Area | Capability |
|---|---|
| **Today** | Command dashboard: overdue items, chase queue, decision-ready topics, key dates, upcoming meetings with agenda-capacity bars |
| **Register** | Single register of **commitments** (promises made to the principal / AET / regulators) and **actions** (the work delivering them), with owners, due dates, chase history and re-chase reminders; one-click export to Excel/CSV (with chase history and links) |
| **Topics** | Discussion items competing for meeting time, with intent (decide / inform / consult / shape), duration and readiness |
| **Meetings** | Forums (recurring governance meetings with a time budget) → meeting instances → **agenda builder** that *ranks* candidate topics with a transparent score and packs them into the capacity, drag-to-reorder, printable agenda, post-meeting decision capture that spawns follow-up actions. Forums and meetings are editable and deletable, with a preflight that names what a delete takes with it. Per forum, a **rolling agenda** shows the next N meetings side by side — the forward view, printable |
| **Planner** | Timeline of every moving part per workstream, hard external deadlines, dependency edges (`blocks` / `precedes`) and **risk chains** — anything downstream of a late/blocked/at-risk item is flagged |
| **Mailbox** | Last 1–5 days of Inbox + Sent Items as a **triage queue**: per email, ranked suggestions of the actions/commitments it probably concerns, then one keystroke to log a chase, spawn an action, close one with the email as evidence, write a People Note, or dismiss. Linked emails are kept forever and are clickable from the record they're attached to |
| **Diary** | Imports `diary.json` from the [Outlook diary extractor](tools/diary_extractor) bundled in this repo; detects rescheduled meetings (cancel + re-create pairs), auto-moves linked meetings, and reconciles attendee display names to people via aliases. Suggests which Outlook events match which Fulcrum meetings, **creates a meeting straight from a diary entry**, clicks through both ways, and prunes old events by date range |
| **People** | The directory behind every owner field, plus **People Notes** (feedback, call notes, observations) and **1:1 packs** — one click gives you everything a person owns, owes, and hasn't discussed with you yet |
| **Modules** | Manifest-registered external tools runnable from the browser with live logs — the seam where future agentic capabilities plug in |
| **Settings** | One-click DB backup, full JSON export, demo-data loader, and scoped clears (demo / diary / mail / everything) |

## Quick start

```bash
# one-off setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# every day
.venv/bin/python run.py          # serves http://localhost:8742 and opens your browser
```

Dev mode (hot reload): run `uvicorn app.main:app --reload --port 8742` from `backend/`, and
`npm run dev` in `frontend/` (Vite proxies `/api`).

Tests: `cd backend && ../.venv/bin/python -m pytest tests` (and `.venv/bin/python -m pytest
tools/mail_extractor/tests tools/diary_extractor/tests` for the extractors' pure layers, which run
anywhere — no Outlook needed).

## Corporate laptop deployment

Designed for a locked-down Windows machine with Python + Node but no Docker/admin:

1. Copy the repo (or `git clone` if allowed). `pip install -r requirements.txt` into a venv.
2. `cd frontend && npm install && npm run build` — needed **once**; after that only Python runs.
3. `python run.py` → browser opens at `localhost:8742`. Everything is local; nothing leaves the machine.
4. Your data is the single file `data/fulcrum.db` (gitignored — **never commit it**). Back it up
   from Settings, restore by putting the file back.

### Feeding it your Outlook diary

`tools/diary_extractor/export_diary.py` runs on the corporate machine against the signed-in desktop
Outlook (Task Scheduler every 15 min works well) and writes `diary.json`. It ships **inside this
repo**, alongside the mail extractor, so there is nothing extra to clone. Then either:

- **Same machine**: the `outlook-diary-extractor` module on the Modules page runs the extractor and
  ingests the output automatically (edit `modules/registry/outlook-diary-extractor.json` to set your
  mailbox, and `cwd` if your checkout isn't at `C:\Dev\CoS`), or
- **Different machine**: transfer `diary.json` and use **Import diary.json** on the Diary page
  (or the `diary-import` module) — or, if browser uploads are DLP-inspected on that machine, skip
  the browser entirely with `python import_data.py diary` (see "Scripted imports" below).

Re-imports are incremental — the extractor's stable event ids make them idempotent.

### Feeding it your mailbox

`tools/mail_extractor/export_mail.py` is the same trick for mail: desktop Outlook COM (Graph
blocked, PowerShell in Constrained Language Mode), writing `mailbox.json`. It ships **inside this
repo**, so there is nothing extra to copy.

```bat
python export_mail.py --days 5 --out data\imports\mailbox.json
```

Run the pre-flight in `tools/mail_extractor/README.md` first — it confirms Outlook COM works and,
more importantly, that SMTP addresses resolve for senders and recipients (on Exchange these often
come back as X.500 DNs; the extractor falls back to GAL resolution, and the pre-flight tells you
which path your tenant takes). Then run it on a Task Scheduler cadence and either use the
`outlook-mail-extractor` module or **Import mailbox.json** on the Mailbox page.

Each run exports the whole window and the importer upserts by message id, so re-imports are
idempotent and never disturb triage state. Mail you have **not** linked to anything is purged after
30 days (override with `FULCRUM_MAIL_RETENTION_DAYS`) to stop the database becoming a mail archive;
anything you linked to an action, commitment or note is kept indefinitely as evidence.

### Scripted imports (no browser)

**On a corporate machine, prefer the scripted importers over the browser upload pages.** Each one
reads a file and writes straight to `data/fulcrum.db` — the content never goes through an HTTP
request, so it never gets near the bank's DLP inspection of browser uploads, and it works while
`run.py` is already running (WAL + a 5s busy-timeout absorb brief writer-lock contention instead of
failing instantly). `import_data.py` is the one entry point for every importer; `import_mail.py`
still works exactly as before — it's shorthand for `python import_data.py mail`:

```bat
python import_mail.py
python import_data.py diary
python import_data.py register data\imports\register.csv
python import_data.py people
```

| Kind | Reads | Default file | `type` |
|---|---|---|---|
| `mail` | mailbox.json | `mailbox.json` | idempotent upsert by message id |
| `diary` | diary.json | `diary.json` | idempotent upsert by event id |
| `register` | CSV/XLSX | `register.csv` | actions/commitments/topics — a `type` column decides each row |
| `actions` | CSV/XLSX | `actions.csv` | same importer as `register`; rows with no `type` column default to action |
| `commitments` | CSV/XLSX | `commitments.csv` | ...default to commitment |
| `topics` | CSV/XLSX | `topics.csv` | ...default to topic |
| `people` | CSV/XLSX | `people.csv` | dedupes against existing people/aliases by name |

| Flag | Effect |
|---|---|
| `--archive` | after a successful import, move the file to `archive/` next to it (timestamped, never overwrites) |
| `--quiet` | print nothing on success |
| `--json` | print a single JSON summary (`{"files": [...], "totals": {...}}`) instead of the human-readable lines |
| `--dry-run` | CSV/XLSX kinds only — run the preview and print what would be created (including unmatched-owner/workstream/meeting warnings and skipped rows), writing nothing |
| `--default-meeting-id N` | `register`/`actions`/`commitments`/`topics` only — link rows whose own meeting reference doesn't match to meeting `N` |

Exit codes: `0` success, `1` unexpected error, `2` path not found (including an unrecognised
`kind`), `3` malformed input, `4` database error (e.g. locked — retry in a moment).

`--archive` and mail retention solve different problems and don't share a clock: retention prunes
the **database** of unlinked mail after 30 days, but `--archive` keeps the raw export — full
plaintext mail bodies included — in `data/imports/archive/` indefinitely, with nothing ever pruning
it; clear that folder out periodically if you use `--archive` on a schedule.

With no PATH argument each kind picks up its default file under `data\imports\`, so a short Task
Scheduler `.bat` chains an extractor straight into Fulcrum. Defaults are working-directory-dependent
— an extractor's relative `--out` resolves against the caller's cwd, while `import_data.py`'s
default is resolved relative to its own file — and Task Scheduler with a blank "Start in" runs jobs
from `%windir%\System32`, so without a `cd` the export would write somewhere the importer never
reads and you'd silently get nothing imported. Make the `.bat` self-locating instead:

```bat
cd /d %~dp0
python tools\mail_extractor\export_mail.py --days 5 --out data\imports\mailbox.json
python import_mail.py --quiet
```

Save this as `fulcrum-mail.bat` in the repo root (or set the scheduled task's "Start in" to the
repo root) so `%~dp0` resolves correctly.

## Adding a module

Drop a manifest into `modules/registry/`:

```json
{
  "name": "my-tool",
  "label": "My tool",
  "description": "What it does",
  "platform": "any",
  "command": ["python", "tool.py", "--flag", "{value}"],
  "cwd": "/path/to/tool",
  "args": [{ "name": "value", "label": "Value", "required": true, "default": "" }],
  "artifact": "/path/to/output.json",
  "ingest": "diary"
}
```

`command` entries may contain `{arg}` placeholders. `"builtin": "diary_import"` instead of
`command` runs an in-process importer. `"ingest": "diary"` auto-imports the artifact after a
successful run. Runs appear on the Modules page with captured logs.

## Architecture

```
run.py                 single entry point (uvicorn on :8742, serves frontend/dist)
import_data.py          scripted (no-browser) import CLI — every kind; import_mail.py is shorthand for `mail`
backend/app/
  models/              SQLAlchemy 2.0 (SQLite, WAL) — people, register, meetings, horizon, mail, ops
  api/                 FastAPI routers — everything is a REST endpoint (docs at /api/docs)
  services/            agenda scoring, quick-add parser, diary + mail import, risk chains,
                       CSV import, register export, seed, cli_import (shared scripted-import harness)
  modules/runner.py    manifest registry + subprocess runner
frontend/              React 19 + Vite + Tailwind 4 (TypeScript), TanStack Query, FullCalendar, dnd-kit
tools/diary_extractor/ Outlook COM calendar export (Windows) — writes diary.json
tools/mail_extractor/  Outlook COM mail export (Windows) over a pure, tested normalisation layer
modules/registry/      module manifests
data/                  fulcrum.db + import inbox (gitignored)
```

Design choices that matter for what comes next:

- **API-first**: every UI capability is an OpenAPI-documented endpoint, so future agents can drive
  the same surface a human does.
- **Module manifests** are the tool-registration mechanism agents will reuse.
- **Generic `link` edges** connect anything to anything (`blocks`, `precedes`, `informs`,
  `relates`) — dependency logic, decision→action trails, topic↔commitment ties and email→record
  evidence all ride on it. A link is also what makes an email permanent: the retention purge skips
  anything referenced by one.
- **`is_demo` flag** on every user-domain row keeps demo data separable from real data.
- Quick-add grammar: `Chase the pack @sarah #credit due:fri !high` (`due:` accepts ISO dates,
  `today`, `tomorrow`, `+N`, weekday names). Switch quick-add's type to **Note** and the same box
  writes a People Note — `handled the walkthrough well @sarah kind:feedback` (the `@person` is
  required; `kind:` is optional).
- **Outlook stays the mail client.** The Mailbox pane is a triage surface, not a mail app — no
  sending, no HTML rendering, no attachments; replies hand off to Outlook via `mailto:`.

## Roadmap — the dream list

Everything below attaches through the existing seams (REST API, module registry, link graph,
`diary.json` transport) — none of it requires reworking the core.

**How to read the scores.**
*Value*: ★★★ = changes how the CoS role is done daily · ★★ = strong weekly payoff · ★ = nice to have.
*Effort*: **S** = under one build session · **M** = 1–2 sessions · **L** = 3–5 sessions · **XL** = multi-week, architectural.
*Cost*: everything runs local and free unless marked. AI items need a Claude API key; realistic usage
(dozens of drafts/briefs a day) is pennies-to-a-few-pounds per month — the only real money anywhere on this list.

### 1 · Intelligence & agentic (the big prize)

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **Chase drafter** | One click on any chase-queue item drafts the nudge email/Teams message — tone calibrated to owner seniority, history of previous chases, and how overdue it is. Copy to clipboard or open in Outlook. | ★★★ | M | API pennies |
| **Morning briefing agent** | At 07:30, generates the day's brief: what changed overnight, what needs chasing, decisions stuck, meetings today with readiness gaps. Delivered as the dashboard PDF or a text digest. | ★★★ | M | API pennies |
| **Meeting pack generator** | Before each forum: agenda + one paragraph of live status per topic (pulled from linked commitments, chases, risk chains) + open decisions. The pre-read writes itself. | ★★★ | M | API pennies |
| **Transcript-to-register (local)** | Paste raw minutes/transcript straight into Fulcrum; extraction happens via the Claude API instead of round-tripping through Teams Copilot. Same import preview. | ★★ | M | API pennies |
| **Ask Fulcrum** | Natural-language questions over the whole graph: "what's at risk for the Audit Committee?", "what has Sarah owned longer than a month?" | ★★ | L | API pennies |
| **Autonomous ops agent** | Claude Agent SDK agent driving the REST API on a schedule: proposes agendas, flags stale items, pre-drafts chases for approval, triages imports. The end-state the platform was designed for. | ★★★ | XL | API £/month |

### 2 · Bank-system integrations

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **SARA ingest module** | Module that reads SARA audit/issue exports; audits become workstreams, issue due dates become key dates, overdue issues feed risk chains. | ★★★ | M–L¹ | free |
| **Diary auto-sync watcher** | Watches a folder (e.g. OneDrive-synced) for a fresh `diary.json` and imports it automatically — zero-touch diary. | ★★ | S | free |
| **Outlook draft handoff** ◐ *part-shipped* | Chases and agendas open as pre-filled Outlook drafts (`.eml`/mailto — no Graph API needed). The Mailbox pane already hands off replies via `mailto:`; the chase-queue and agenda paths remain. | ★★ | S | free |
| **Mailbox triage pane** ✅ *shipped* | `export_mail.py` (COM, sibling of the diary extractor) feeds Inbox + Sent Items into a triage pane: suggestions rank matching actions per email; log chases, spawn/close actions, push People Notes, dismiss — one keystroke per email. | ★★★ | L | free |
| **SharePoint push + Power Automate chaser** | Diff-export actions into a OneDrive-synced library folder; flows upsert a SharePoint List and send throttled per-owner chase emails. No Graph anywhere. | ★★★ | M | free |
| **Teams deep links** | Meetings carry a "Join"/chat link; topics link to their Teams channel. | ★ | S | free |

¹ depends on what SARA can export (CSV/Excel assumed; an API would be L).

### 3 · Planning engine upgrades

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **Critical-path scheduling** | Real earliest/latest dates and slack across the dependency graph; move one date and watch the cascade recompute. Turns the planner from a picture into an engine. | ★★★ | L | free |
| **Scenario mode** | "What if S166 slips two weeks?" — preview the downstream impact without committing it. | ★★ | M | free |
| **Owner capacity heatmap** ✅ *shipped* | Who is carrying how much, by week — spot the overloaded director before they miss. | ★★ | M | free |
| **Recurring commitments** | Weekly status notes etc. auto-regenerate on their cadence instead of being re-keyed. | ★★ | S | free |
| **Milestones & swimlane export** | Workstream milestones plus the polished printable swimlane (the one genuinely good bit of DynoCal). | ★ | M | free |

### 4 · Meeting engine upgrades

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **Rolling agenda (single pane of glass)** ✅ *shipped* | A forum's next N meetings side by side — dates across the top, topics banded by workstream down the side, intent as the cell colour and capacity metered per date. Prints landscape for presenting the forward view at ad-hoc meetings; replaces the hand-built Excel grid. | ★★★ | M | free |
| **Rolling agenda: unscheduled backlog column** | A right-hand column of topics not yet on any date, so the forward view shows what is waiting as well as what is placed. Needs a topic↔forum affinity first, otherwise it is a cross-forum dump. | ★★ | M | free |
| **Move an agenda item between meetings** | A single-transaction `PATCH /agenda-items/{id}` carrying `meeting_id`, so a topic can be dragged from one date to another in the rolling grid. Today's only route is delete + re-add, which is non-atomic and resets the topic's status — hence drag is deliberately out of the rolling view. | ★★ | S–M | free |
| **Forward agenda planning** | Plan topics across the *next several* instances of a forum; parked items auto-carry; see forum congestion weeks out. | ★★★ | M | free |
| **Cadence auto-generation** | Structured cadence rules ("weekly Mon 10:00") generate meeting instances automatically. | ★★ | S | free |
| **Minutes & actions pack** | Post-meeting one-pager: outcomes, decisions, spawned actions with owners — exportable like the daily brief. | ★★ | S–M | free |
| **Attendance intelligence** | From the diary: who was double-booked, declined patterns, chair-time analysis per forum. | ★ | M | free |

### 5 · Principal & people support

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **1:1 packs** ✅ *shipped* | One click per person: everything they own, overdue, promised, and decisions awaiting them — walk into any 1:1 armed. | ★★★ | S | free |
| **Weekly principal report builder** | Curated weekly pack (delivered/slipped/decisions needed/horizon) as PDF; the daily-brief pipeline generalised. | ★★ | M | free |
| **Decision review dates** ✅ *shipped* | Decisions carry a revisit date and resurface on the dashboard when due — "we said we'd look at this again in Q4" never gets lost. | ★★ | S | free |
| **People Notes** ✅ *shipped* | Feedback, call notes and observations tagged to a person (`note @sarah … kind:feedback`); undiscussed notes surface in the 1:1 pack and sweep clear after the conversation. | ★★ | S | free |
| **Data quality panel** | Unowned items, missing due dates, stale statuses, unlinked meetings — keeps the register trustworthy, which everything else depends on. | ★★ | S | free |

### 6 · Platform & quality of life

| Feature | What it does | Value | Effort | Cost |
|---|---|---|---|---|
| **Global search (Ctrl+/)** ✅ *shipped* | Full-text across actions, commitments, topics, decisions, diary, chase notes. | ★★ | S–M | free |
| **Register export** ✅ *shipped* | Whole register to an Excel workbook or CSV zip, optionally with chase history and the link/dependency graph — the artefact you attach to a paper or hand to a BPM. | ★★ | S | free |
| **Item history / audit trail** | What changed and when on every item — evidence-grade record keeping, fitting for an audit function. | ★★ | M | free |
| **Notifications** | Local scheduled task fires Windows toasts / digest emails for chases due and hard deadlines approaching. | ★★ | M | free |
| **Automated versioned backups** | Snapshot `fulcrum.db` on every launch, keep N days — recover from anything. | ★★ | S | free |
| **Mobile-friendly capture (PWA)** | Responsive quick-add for corridor moments. | ★ | M | free |
| **Multi-user for BPMs** | Auth, per-user assignment views, comments; the BPM team works *in* Fulcrum rather than around it. | ★★ | XL | free² |

² unless hosted centrally, which brings bank infra questions well beyond the tool.

### Suggested order of attack

High value ÷ low effort first, and each step feeds the next:

1. **SharePoint push + Power Automate chaser** — closes the loop the Mailbox pane opened: Fulcrum
   stops being the only place the register lives, and owners get chased without the CoS typing
   anything. Needs no Graph — a OneDrive-synced library folder is the transport.
2. **Data quality panel** + **automated backups** + **diary auto-sync watcher** (three S items that
   remove routine friction and keep the register trustworthy)
3. **Chase drafter** — first AI feature; the chase queue and the mail history now supply perfect
   context, and the Mailbox action rail is the natural home for it
4. **Meeting pack generator** + **forward agenda planning** (the meeting engine becomes decisive)
5. **SARA ingest** (when an export path is confirmed)
6. **Critical-path scheduling**, then the **morning briefing agent**, building toward the
   **autonomous ops agent**

Shipped so far: the whole **Outlook bridge** (mail extractor → ingest → triage pane → verbs →
click-through evidence), **People Notes**, **register export**, plus the earlier 1:1 packs, decision
review dates, capacity heatmap, recurring topics and global search.

### Known gaps — deliberately deferred

Found by review, judged not worth blocking a release, and recorded here so they are not rediscovered
as surprises. None of them affects the documented day-to-day flows.

| Gap | Why it matters | Effort |
|---|---|---|
| **`people --dry-run` can disagree with a real commit** | `import_data.py`'s `_simulate_people_commit` re-implements `commit_people`'s counting instead of calling it, so across a *multi-file* run it can't see people an earlier file would have created and over-counts. Single-file runs agree exactly. This is the one live exception to the two-doors rule in `CLAUDE.md`; the clean fix is a real commit followed by a rollback, which needs a `commit=False` parameter on the shared service. | M |
| **A bad file aborts the rest of a directory import** | CLI directory mode stops at the first malformed file and the remaining files are neither imported nor mentioned — on a schedule it repeats the same abort forever. Should collect per-file errors and continue. | M |
| **CLI's two headline properties are untested** | That the importer makes no network calls, and that a locked database exits 4, were both verified by hand; nothing stops a refactor silently breaking either. | M |
| **Upload endpoints keep every uploaded file forever** | Including malformed ones, in `data/imports/` — they accumulate and then break directory-mode imports. Wants a cleanup or a temp-file approach. | S |
| **`PATCH` with an explicit `null` on a non-nullable column returns 500** | Project-wide consequence of the `exclude_unset` + `setattr` idiom, not specific to any one endpoint; fixing it in one place only would break the consistency. | M |
| **`dismiss-bulk` has no UI** | The endpoint and its tests exist; the Mailbox list has no multi-select. The `BulkSelect` pattern used on Register/Topics/People would drop straight in. | S |
