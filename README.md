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
| **Meetings** | Forums (recurring governance meetings with a time budget) → meeting instances → **agenda builder** that *ranks* candidate topics with a transparent score and packs them into the capacity, drag-to-reorder, printable agenda, post-meeting decision capture that spawns follow-up actions |
| **Planner** | Timeline of every moving part per workstream, hard external deadlines, dependency edges (`blocks` / `precedes`) and **risk chains** — anything downstream of a late/blocked/at-risk item is flagged |
| **Mailbox** | Last 1–5 days of Inbox + Sent Items as a **triage queue**: per email, ranked suggestions of the actions/commitments it probably concerns, then one keystroke to log a chase, spawn an action, close one with the email as evidence, write a People Note, or dismiss. Linked emails are kept forever and are clickable from the record they're attached to |
| **Diary** | Imports `diary.json` from the [Outlook Diary Extractor](../OutlookDiaryExtractor); detects rescheduled meetings (cancel + re-create pairs), auto-moves linked meetings, and reconciles attendee display names to people via aliases |
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
tools/mail_extractor/tests` for the extractor's pure layer, which runs anywhere — no Outlook needed).

## Corporate laptop deployment

Designed for a locked-down Windows machine with Python + Node but no Docker/admin:

1. Copy the repo (or `git clone` if allowed). `pip install -r requirements.txt` into a venv.
2. `cd frontend && npm install && npm run build` — needed **once**; after that only Python runs.
3. `python run.py` → browser opens at `localhost:8742`. Everything is local; nothing leaves the machine.
4. Your data is the single file `data/fulcrum.db` (gitignored — **never commit it**). Back it up
   from Settings, restore by putting the file back.

### Feeding it your Outlook diary

The Outlook Diary Extractor runs on the corporate machine against the signed-in desktop Outlook
(Task Scheduler every 15 min works well) and writes `diary.json`. Then either:

- **Same machine**: the `outlook-diary-extractor` module on the Modules page runs the extractor and
  ingests the output automatically (edit `modules/registry/outlook-diary-extractor.json` to point
  `cwd` at your extractor checkout and set your mailbox), or
- **Different machine**: transfer `diary.json` and use **Import diary.json** on the Diary page
  (or the `diary-import` module).

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

**On a corporate machine, prefer `import_mail.py` over the browser upload.** It reads
`mailbox.json` and writes straight to `data/fulcrum.db` — the content never goes through an HTTP
request, so it never gets near the bank's DLP inspection of browser uploads, and it works while
`run.py` is already running:

```bat
python import_mail.py
```

| Flag | Effect |
|---|---|
| `--archive` | after a successful import, move the file to `archive/` next to it (timestamped, never overwrites) |
| `--quiet` | print nothing on success |
| `--json` | print a single JSON summary (`{"files": [...], "totals": {...}}`) instead of the human-readable lines |

Exit codes: `0` success, `1` unexpected error, `2` path not found, `3` malformed `mailbox.json`,
`4` database error (e.g. locked — retry in a moment).

`--archive` and retention solve different problems and don't share a clock: retention prunes the
**database** of unlinked mail after 30 days, but `--archive` keeps the raw export — full plaintext
bodies included — in `data/imports/archive/` indefinitely, with nothing ever pruning it; clear that
folder out periodically if you use `--archive` on a schedule.

With no argument it picks up `data\imports\mailbox.json`, so a two-line Task Scheduler `.bat` chains
the extractor straight into Fulcrum. Both defaults are working-directory-dependent —
`export_mail.py`'s relative `--out` resolves against the caller's cwd, while `import_mail.py`'s
default is resolved relative to its own file — and Task Scheduler with a blank "Start in" runs jobs
from `%windir%\System32`, so without a `cd` the export would write somewhere the importer never
reads and you'd silently get no mail. Make the `.bat` self-locating instead:

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
backend/app/
  models/              SQLAlchemy 2.0 (SQLite, WAL) — people, register, meetings, horizon, mail, ops
  api/                 FastAPI routers — everything is a REST endpoint (docs at /api/docs)
  services/            agenda scoring, quick-add parser, diary + mail import, risk chains,
                       CSV import, register export, seed
  modules/runner.py    manifest registry + subprocess runner
frontend/              React 19 + Vite + Tailwind 4 (TypeScript), TanStack Query, FullCalendar, dnd-kit
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
