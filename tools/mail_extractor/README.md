# Mail Extractor

Exports the last N days of Outlook **Inbox + Sent Items** to a `mailbox.json`
file for the Fulcrum backend to import, using **desktop Outlook COM
automation** (Microsoft Graph is blocked on the target machine).

Standalone sibling to `/home/cp/Dev/OutlookDiaryExtractor` (the calendar
extractor) — same rationale, same COM-attach pattern, same
pure-logic/COM-layer split, but produces mail, not calendar events, and
rewrites its full window on every run rather than doing an incremental merge
(the Fulcrum importer upserts idempotently by `id`, so there is no need for a
local merge step here).

- `export_mail.py` — CLI entry point + the thin COM harvest layer
  (Windows-only; imports `pywin32` **lazily**, only when it actually reaches
  Outlook, so the module still imports cleanly on Linux/macOS).
- `mail_normalize.py` — **all** pure logic: normalizing raw per-message
  values into the output schema, body truncation, id fallback, recipient
  shaping, the `meta` block, and full-document assembly. Stdlib only, no COM,
  no file IO — imports and unit-tests on any platform.
- `tests/` — pytest tests for the pure layer, using fake values (no live
  Outlook needed).

---

## Pre-flight (locked-down Windows machine)

Confirm Python can drive Outlook COM (Outlook should already be running and
signed in):

```bat
python -c "import win32com.client as w; print(w.Dispatch('Outlook.Application').Session.CurrentUser.Name)"
```

If it prints your name, COM works. If the import fails, install `pywin32`:

```bat
pip install pywin32
```

On a corporate build without direct PyPI access, point pip at the internal
mirror, e.g. `pip install --index-url https://<your-internal-mirror>/simple pywin32`.

Requirements:

- Windows with the desktop Outlook client **running and signed in**.
- Python 3.8+ and `pywin32`.
- For `--mailbox`: the target mailbox must already be added to the Outlook
  profile (as a full account or an opened shared mailbox) so it shows up in
  `Namespace.Folders`.
- The tool **attaches** to the running Outlook instance and never calls
  `.Quit()` — it will not close the user's Outlook.

---

## Usage

Default: last 5 days, own mailbox, writes `./mailbox.json`:

```bat
python export_mail.py
```

Different window:

```bat
python export_mail.py --days 14
```

Custom output path:

```bat
python export_mail.py --days 5 --out "C:\Fulcrum\mailbox.json"
```

Delegate / shared mailbox (resolved via `Namespace.Folders` by display name;
falls back to the signed-in user's own mailbox if the name can't be found):

```bat
python export_mail.py --days 5 --mailbox "Shared Team Mailbox"
```

### Parameters

| Parameter    | Default            | Meaning                                                              |
|--------------|--------------------|------------------------------------------------------------------------|
| `--days`     | `5`                | Number of days back from now to include (Inbox + Sent Items).         |
| `--out`      | `./mailbox.json`   | Output JSON path (written atomically; directory auto-created).        |
| `--mailbox`  | (none)             | Delegate/shared mailbox display name. Default: signed-in user's own mailbox (`meta.mailbox` = `"default"`). |

Exit codes: `2` for usage errors (`--days <= 0`), `1` for runtime failures
(Outlook not attachable), `0` on success.

Each run **rewrites the full current window** — there is no incremental
merge file. The Fulcrum importer upserts idempotently by `id`, so re-running
on a schedule is safe and simply refreshes the window.

On a corporate machine, feed the output into Fulcrum with the repo-root
`import_mail.py` script rather than the Mailbox page's browser upload — it
reads `mailbox.json` and writes straight to `data/fulcrum.db`, so the mail
content never goes through an HTTP request and never trips DLP inspection of
browser uploads. See "Feeding it your mailbox" in the top-level `README.md`
for the two-line Task Scheduler `.bat` that chains this extractor into it,
including `import_mail.py`'s `--archive`/`--quiet`/`--json` flags and exit
codes.

---

## Scheduling (Task Scheduler)

Create a task that runs while the user is logged on (Outlook must be
running):

- **Program/script:** `python.exe` (or the full path, e.g.
  `C:\Python312\python.exe`)
- **Add arguments:**

  ```
  "C:\Dev\CoS\tools\mail_extractor\export_mail.py" --days 5 --out "C:\Dev\CoS\data\imports\mailbox.json"
  ```

- **Trigger:** e.g. every 15–30 minutes.
- Run **only when user is logged on** (COM needs the interactive Outlook
  session).

Or register from a prompt:

```bat
schtasks /Create /TN "MailExtractor" /SC MINUTE /MO 15 /TR "python.exe \"C:\Dev\CoS\tools\mail_extractor\export_mail.py\" --days 5 --out \"C:\Dev\CoS\data\imports\mailbox.json\"" /RL LIMITED /F
```

`data\imports\mailbox.json` (relative to the repo root) is the canonical output location — it's
where `import_mail.py` looks by default with no argument, and it's the `out_file` default in the
`outlook-mail-extractor` module manifest (`modules/registry/outlook-mail-extractor.json`) — keep
all three in sync if the deployment path ever changes.

---

## Output JSON (frozen contract)

```json
{
  "meta": {
    "generated_at": "2026-08-18T18:00:00Z",
    "mailbox": "default",
    "window_days": 5,
    "tool": "export_mail",
    "version": 1,
    "skipped": 0
  },
  "messages": [
    {
      "id": "<abc123@mail.example.com>",
      "conversation_id": "AAQkAG...",
      "folder": "inbox",
      "subject": "Re: Quarterly review",
      "sender_name": "Alice Smith",
      "sender_email": "alice.smith@yourorg.com",
      "to": [ { "name": "Bob Jones", "email": "bob.jones@yourorg.com" } ],
      "cc": [],
      "sent_at": "2026-08-18T09:00:00+01:00",
      "received_at": "2026-08-18T09:00:05+01:00",
      "body_text": "Hi Bob, ...",
      "has_attachments": false
    }
  ]
}
```

### `meta` fields

| Field          | Type   | Notes                                                              |
|----------------|--------|----------------------------------------------------------------------|
| `generated_at` | string | UTC ISO-8601, `...Z`, when this run finished.                        |
| `mailbox`      | string | The `--mailbox` display name, or `"default"` when omitted.           |
| `window_days`  | int    | The `--days` value used for this run.                                |
| `tool`         | string | Always `"export_mail"`.                                              |
| `version`      | int    | Schema version, currently `1`.                                       |
| `skipped`      | int    | Count of items skipped while harvesting (non-mail items or read errors); one skip never aborts the run. |

### `messages[]` fields

| Field             | Type            | Notes                                                                 |
|-------------------|-----------------|-------------------------------------------------------------------------|
| `id`              | string          | `PR_INTERNET_MESSAGE_ID` if present; else `"entryid:" + EntryID`. Stable merge key; unique within a run (de-duplicated). |
| `conversation_id` | string or null  | Outlook `ConversationID`, or `null` if unavailable.                     |
| `folder`          | string          | `"inbox"` or `"sent"`.                                                  |
| `subject`         | string          | Message subject (`""` if unreadable).                                   |
| `sender_name`     | string          | Sender display name.                                                    |
| `sender_email`    | string          | Sender SMTP address, resolved with a 3-step fallback (see below); `""` if none resolve. |
| `to`              | array           | `[{"name": "...", "email": "..."}]`.                                    |
| `cc`              | array           | Same shape as `to`.                                                     |
| `sent_at`         | string or null  | ISO 8601 with local offset (`SentOn`); `null` if unavailable.           |
| `received_at`     | string or null  | ISO 8601 with local offset (`ReceivedTime`); `null` if unavailable.     |
| `body_text`       | string          | Plain-text body, truncated to 32000 characters.                         |
| `has_attachments` | bool            | `Attachments.Count > 0`.                                                |

The file is written atomically (`mailbox.json.tmp` then `os.replace`), so a
downstream reader never sees a torn file. Encoding is UTF-8 without BOM.

**Invariant:** Fulcrum derives each message's `occurred_date` (the day-window
filter key) from the local-offset `sent_at`/`received_at` strings above by
truncating to a calendar date — it does no timezone conversion. This assumes
the extractor and the Fulcrum backend run on the same machine (or at least
the same timezone); running them in different timezones will shift which day
a message lands on in the UI.

---

## Timezones

**The pywin32 gotcha:** COM datetimes handed back by pywin32/pywintypes
(`item.SentOn`, `item.ReceivedTime`) are *not* naive, but they're not
honestly timezone-aware either — `tzinfo` is a fixed zero/UTC offset while
the wall-clock fields (year/month/day/hour/minute) are already local time.
Code that does `if dt.tzinfo is None: attach local tz` never fires that
branch on a real COM value, so the mislabelled datetime passes straight
through and gets formatted as local wall clock stamped `+00:00` — wrong by
the DST offset (e.g. an hour, in UK summer) as an actual instant in time,
even though the printed string looks plausible. Downstream this shows up as
`sent_at`/`received_at` being an hour off, and `occurred_date` day-bucketing
near midnight landing on the wrong day.

**Correct handling:** `_ensure_aware()` in `export_mail.py` discards the COM
tzinfo and re-derives it from the wall clock: `dt.replace(tzinfo=None)`
strips the bogus offset to give a naive datetime holding the (correct) local
wall clock, then `.astimezone()` interprets that naive value as local time
and attaches the right offset **for that specific date**, so DST is
resolved per-date rather than inherited from whatever offset COM handed us.
Mirrors `OutlookDiaryExtractor/export_diary.py`'s `_ensure_aware`.

---

## COM implementation notes

**Restrict() date format.** `Items.Restrict("[ReceivedTime] >= '<date>'")`
parses its date literal as US short-date + 12-hour time
(`%m/%d/%Y %I:%M %p`, e.g. `08/13/2026 09:00 AM`) regardless of the message
property involved — passing an ISO string or a non-US day/month order
silently returns zero or the wrong results rather than raising. See
`format_restrict_datetime()` in `export_mail.py` for the exact formatting and
a fuller comment on the gotcha (and how it differs from the sibling diary
tool's locale-aware approach).

**Sender SMTP resolution** (`_resolve_sender_email`) tries, in order:

1. `PropertyAccessor.GetProperty(PR_SENDER_SMTP_ADDRESS)` — the reliable,
   type-agnostic source.
2. `SenderEmailAddress`, only when `SenderEmailType == "SMTP"` (otherwise
   it's a legacy X.500 DN, not usable as an address).
3. `Sender.GetExchangeUser().PrimarySmtpAddress` — GAL resolution, for
   internal senders the first two steps missed.

Each step is independently `try`/`except`-guarded; failure falls through to
the next.

**Recipient SMTP resolution** (`_resolve_recipient_email`) is the analogous
per-recipient version: `PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)` first,
then `AddressEntry.GetExchangeUser().PrimarySmtpAddress`, then
`AddressEntry.Address`.

**Per-item resilience.** Every item in the Restrict()'d collection is
extracted inside its own `try`/`except` (`_harvest_folder`); a single
corrupt/unreadable item, or an item whose `Class` isn't `MailItem` (43) —
e.g. a meeting request or read receipt sitting in Inbox — is counted in
`meta.skipped` and the run continues.

---

## Testing

The pure layer (`mail_normalize.py`) has **no COM dependency** and is tested
with pytest from the repo root:

```bash
cd /home/cp/Dev/CoS && .venv/bin/python -m pytest tools/mail_extractor/tests -q
```

The suite pins the full frozen output contract (`build_output`'s shape,
field order, and `meta` block), body truncation at exactly 32000 characters,
id fallback (`entryid:` prefix), recipient shaping, and within-run
de-duplication by `id`. It also asserts that neither `mail_normalize.py` nor
`export_mail.py` imports `win32com` at module load time, so both import
cleanly on Linux/macOS for CI and local development. The COM layer itself
(`export_mail.py`'s harvest functions) is not unit-tested — it needs a real
Outlook — so verify a change there with one live run on Windows and a review
of the resulting `mailbox.json`.

---

## Troubleshooting

**`import win32com.client` fails (`ModuleNotFoundError`).** `pywin32` is not
installed for the Python you invoked. Run `pip install pywin32` (see
[Pre-flight](#pre-flight-locked-down-windows-machine)).

**"Could not attach to Outlook ..."** (exit 1) The desktop Outlook client is
not running. Start Outlook, wait for it to finish loading, and re-run.

**`--mailbox` silently falls back to the default mailbox.** The named store
wasn't found in `Namespace.Folders`, or it doesn't expose a subfolder named
exactly `Inbox` / `Sent Items` (e.g. some shared-mailbox configurations lack
a usable Sent Items). Confirm the mailbox is visible in Outlook's folder
pane under exactly that display name; add it to the profile first if it
isn't.

**Wrong / no messages, or a `Restrict` error about dates.** See
[COM implementation notes](#com-implementation-notes) above — `Restrict()`
requires the fixed `%m/%d/%Y %I:%M %p` literal format; verify the window
printed at the top of the run looks right.

**High `meta.skipped` count.** Expected for folders containing non-mail
items (meeting requests, read receipts, IPM.Note variants). If it seems too
high, check stderr isn't reporting a systematic per-item failure (e.g. a
permissions issue) rather than genuine non-mail items.
