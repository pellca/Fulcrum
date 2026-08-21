# Working on Fulcrum

Conventions that are not obvious from the code, and the reasoning behind them. Read before adding a
feature; the deployment target is unusual and it shapes most of these.

## The deployment target

Fulcrum runs on a **locked-down corporate bank laptop**: Python and Node are allowed, Docker and
admin rights are not, Microsoft Graph is blocked, PowerShell runs in Constrained Language Mode, and
**DLP inspects browser uploads**. Development happens on Linux; only the built frontend and Python
ship. Everything is local — no data leaves the machine, and `data/` is gitignored.

Two consequences that catch people out:

- **Anything that moves real content through a browser upload will hit DLP.** That is why every
  importer has a CLI twin (below). Assume the same wall for any future feature that ships content
  through the browser.
- **Windows Task Scheduler runs with the working directory set to `%windir%\system32`.** Any `.bat`
  we document must start with `cd /d %~dp0`, or relative paths silently resolve somewhere nobody
  looks — no error, just nothing happening.

## Every importer needs two doors

**Rule: an importer is not finished until it has both an API path and a scripted path.** They must
share one service function, so the two doors cannot drift. Known, tracked exception: the people
importer's `--dry-run` preview is simulated by a second function (`import_data.py`'s
`_simulate_people_commit`) that mirrors `commit_people`'s counting logic read-only rather than
calling it — a real drift risk, pending consolidation, not a pattern to copy for a new importer.

```
backend/app/services/<thing>_import.py   the ONLY place import logic lives
backend/app/api/<thing>.py               HTTP door for mail/diary — upload/path endpoints for the UI
backend/app/api/imports.py               HTTP door for register (actions/commitments/topics) and people
import_data.py <kind>                    CLI door    — no HTTP, writes straight to SQLite
```

The CLI door exists because of DLP, but it earns its keep anyway: it works headless, it schedules,
and it does not need the server running (though it works fine alongside a running server — SQLite
WAL plus `PRAGMA busy_timeout=5000` absorbs the contention).

When adding a new importer:

1. Put the logic in a service function that takes `(db, ...)` and returns a counts dict.
2. Wire the HTTP endpoints to it.
3. Register the kind in the CLI harness — do not write a bespoke script; reuse the shared harness so
   the flags (`--archive`, `--quiet`, `--json`, `--dry-run`), the exit codes and the output shape
   stay identical across kinds.
4. Document both doors in the README, and give the CLI kind a default filename under `data/imports/`
   so the no-argument form works in a scheduled task.

Exit-code contract for every CLI importer: `0` ok, `1` unexpected, `2` file/path not found,
`3` malformed content, `4` database locked. Scheduled tasks discard stderr, so exit codes are the
only signal the user gets.

## Importing is an upsert, and input is never trusted

Imports must be **idempotent** — re-importing the same file changes nothing and never duplicates.
Files are usually a full window (mail, diary), not a delta, so re-runs are routine.

**De-duplicate the input before the write loop.** This is a real bug we shipped once: with
`autoflush=False` (see `backend/app/db.py`), an object that has been `db.add()`ed with a
manually-assigned primary key is *not* visible to `db.get()` or to a query — it only sits in
`session.new` until flushed. So a file containing the same id twice produces two INSERTs and the
whole import dies on a primary-key collision at flush time. Duplicate ids happen in real exports and
we cannot fix them at source, because the extractors run on a different machine.

Also: preserve user-owned state on re-import (mail keeps its triage state), report what happened
honestly in the counts dict (including entries dropped as duplicates), and raise `ValueError` for
malformed content so the HTTP layer can return 422 and the CLI can exit 3.

## Other things worth knowing

- **API-first.** Every UI capability is an OpenAPI-documented endpoint so future agents can drive the
  same surface a human does. Request bodies should get typed Pydantic models, not a bare `dict` — an
  endpoint missing from the schema (or one that accepts an untyped body) is a defect, not a shortcut,
  even though a few pre-existing endpoints still do this and haven't all been cleaned up yet.
- **`Link` edges carry meaning.** `from_type`/`from_id` → `to_type`/`to_id` connects anything to
  anything, and **a link is what makes a record permanent**: mail retention skips any message a link
  references. Ids on the Link table are integers, so anything linkable needs an integer primary key.
- **User-domain tables (people, register, meetings, horizon, ops — the stuff a person creates by
  hand) carry `is_demo`** and belong in the demo-clear table list, so the user can always separate
  demo data from real data. High-volume *imported* tables (`MailMessage`, `DiaryEvent`) don't have
  `is_demo` — they instead have their own dedicated clear scopes (mail/diary), since they're cleared
  on their own retention/re-import logic, not as demo data. A join table hanging off a `is_demo`-less
  parent (e.g. `PersonAlias`, `Chase`, `Link`, `AgendaItem`) generally doesn't need its own `is_demo`
  either — check `clear_data()` in `backend/app/api/admin.py` for the actual clear-scope membership
  of a new table (the "demo" scope deletes from any table that happens to have an `is_demo` column;
  "diary"/"mail" are separate scopes with their own table lists) rather than assuming every table
  needs the column.
- **New tables need no migration** (`create_all` handles them); new *columns on existing tables* do —
  add them to `_COLUMN_MIGRATIONS` in `backend/app/db.py`.
- **Outlook stays the mail client.** The Mailbox pane is a triage surface: no sending, no HTML
  rendering, no attachments. Replies hand off via `mailto:`.
- **Never commit `data/`.** It holds the real register, real mail bodies and real people notes.
- **pywin32 COM datetimes lie about their zone.** They arrive aware with a zero (UTC-labelled)
  offset while the wall-clock fields are already local. Never write `if dt.tzinfo is None` against
  them — re-anchor with `dt.replace(tzinfo=None).astimezone()`.
- **Both Outlook extractors live in `tools/`** (`diary_extractor`, `mail_extractor`) and are
  deliberately siblings: they share the same COM patterns, and the timezone bug above existed in
  *both* copies precisely because the second was written in a separate repo from the first. A fix or
  a gotcha found in one is a prompt to check the other. Each is a thin COM harvest layer over pure,
  testable logic — keep that split, because the COM layer cannot be tested off Windows.

## Testing

- Backend: `cd backend && ../.venv/bin/python -m pytest tests`
- Extractors: `.venv/bin/python -m pytest tools/mail_extractor/tests tools/diary_extractor/tests`
  (pure layers, no Outlook needed — the COM layer in each is deliberately thin so the tested part
  runs anywhere)
- Frontend: `cd frontend && npm run build && npm run lint`

Tests must never touch `data/fulcrum.db` — `conftest.py` points `FULCRUM_DB` at a temp file, and any
test invoking a CLI script must pass that env through.
