# Fulcrum

**Chief of Staff operating platform** — a local, browser-based tool that links commitments,
actions, meeting agendas and forward planning into one system, built for the Chief of Staff of an
Internal Audit & Investigations function.

> *The leverage point: small, well-placed effort moving heavy things.*

## What it does

| Area | Capability |
|---|---|
| **Today** | Command dashboard: overdue items, chase queue, decision-ready topics, key dates, upcoming meetings with agenda-capacity bars |
| **Register** | Single register of **commitments** (promises made to the principal / AET / regulators) and **actions** (the work delivering them), with owners, due dates, chase history and re-chase reminders |
| **Topics** | Discussion items competing for meeting time, with intent (decide / inform / consult / shape), duration and readiness |
| **Meetings** | Forums (recurring governance meetings with a time budget) → meeting instances → **agenda builder** that *ranks* candidate topics with a transparent score and packs them into the capacity, drag-to-reorder, printable agenda, post-meeting decision capture that spawns follow-up actions |
| **Planner** | Timeline of every moving part per workstream, hard external deadlines, dependency edges (`blocks` / `precedes`) and **risk chains** — anything downstream of a late/blocked/at-risk item is flagged |
| **Diary** | Imports `diary.json` from the [Outlook Diary Extractor](../OutlookDiaryExtractor); detects rescheduled meetings (cancel + re-create pairs), auto-moves linked meetings, and reconciles attendee display names to people via aliases |
| **Modules** | Manifest-registered external tools runnable from the browser with live logs — the seam where future agentic capabilities plug in |
| **Settings** | One-click DB backup, full JSON export, demo-data loader, and scoped clears (demo only / diary only / everything) |

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

Tests: `cd backend && ../.venv/bin/python -m pytest tests`

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
  models/              SQLAlchemy 2.0 (SQLite, WAL) — people, register, meetings, horizon, ops
  api/                 FastAPI routers — everything is a REST endpoint (docs at /api/docs)
  services/            agenda scoring, quick-add parser, diary import, risk chains, CSV import, seed
  modules/runner.py    manifest registry + subprocess runner
frontend/              React 19 + Vite + Tailwind 4 (TypeScript), TanStack Query, FullCalendar, dnd-kit
modules/registry/      module manifests
data/                  fulcrum.db + import inbox (gitignored)
```

Design choices that matter for what comes next:

- **API-first**: every UI capability is an OpenAPI-documented endpoint, so future agents can drive
  the same surface a human does.
- **Module manifests** are the tool-registration mechanism agents will reuse.
- **Generic `link` edges** connect anything to anything (`blocks`, `precedes`, `informs`,
  `relates`) — dependency logic, decision→action trails and topic↔commitment ties all ride on it.
- **`is_demo` flag** on every user-domain row keeps demo data separable from real data.
- Quick-add grammar: `Chase the pack @sarah #credit due:fri !high` (`due:` accepts ISO dates,
  `today`, `tomorrow`, `+N`, weekday names).

## Roadmap seams (not yet built)

SARA case-management ingest, Microsoft Graph (if ever approved), automated chase-email drafting,
multi-user for BPMs, agentic execution of chases and agenda assembly — all designed to attach via
the REST API and module registry without reworking the core.
