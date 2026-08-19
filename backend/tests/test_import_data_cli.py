"""Tests for the root-level `import_data.py` CLI (WP-6.2): the DLP-safe scripted
import approach generalised from `import_mail.py` (WP-5.1) to every importer — mail,
diary, the CSV/XLSX action/commitment/topic register, and people.

Invoked via subprocess (not imported), same reasoning as test_import_mail_cli.py:
each test gets its own process with its own FULCRUM_DB override, since the script
binds SQLAlchemy's engine to config.DB_PATH at import time. None of these tests ever
touch data/fulcrum.db.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "import_data.py"

TODAY = date.today().isoformat()

DEFAULT_FILES = {
    "mail": "mailbox.json",
    "diary": "diary.json",
    "register": "register.csv",
    "actions": "actions.csv",
    "commitments": "commitments.csv",
    "topics": "topics.csv",
    "people": "people.csv",
}


def run_cli(args, db_path: Path, cwd: Path | None = None):
    env = dict(os.environ)
    env["FULCRUM_DB"] = str(db_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        cwd=str(cwd or REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _query(db_path: Path, sql: str) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


# --- fixture builders -------------------------------------------------------


def _msg(msg_id, subject="Subject", **overrides):
    base = {
        "id": msg_id,
        "conversation_id": None,
        "folder": "inbox",
        "subject": subject,
        "sender_name": "Alex Morgan",
        "sender_email": "alex.morgan@bank.com",
        "to": [],
        "cc": [],
        "sent_at": None,
        "received_at": f"{TODAY}T09:00:00Z",
        "body_text": "Body text",
        "has_attachments": False,
    }
    base.update(overrides)
    return base


def _write_mailbox(path: Path, messages: list[dict]) -> Path:
    payload = {
        "meta": {"generated_at": f"{TODAY}T09:00:00Z", "mailbox": "delegate@bank.com", "version": 1},
        "messages": messages,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


APPT = "040000008200E00074C5B7101A82E0080000000010203040"


def _event(occurrence: str, **overrides) -> dict:
    base = {
        "id": f"{APPT}|{occurrence}",
        "subject": "AET Weekly",
        "startDate": occurrence[:10],
        "startTime": "10:00",
        "endDate": occurrence[:10],
        "endTime": "11:00",
        "start": f"{occurrence[:10]}T10:00:00+01:00",
        "end": f"{occurrence[:10]}T11:00:00+01:00",
        "organizer": "Alex Morgan",
        "requiredAttendees": [],
        "optionalAttendees": [],
        "location": "Room 4",
        "categories": [],
        "isRecurring": False,
        "isAllDay": False,
        "status": "active",
        "lastModified": "2026-07-28T09:00:00Z",
        "cancelledAt": None,
    }
    base.update(overrides)
    return base


def _write_diary(path: Path, events: list[dict]) -> Path:
    payload = {
        "meta": {
            "mailbox": "cae.office@bank.com",
            "lastRunUtc": "2026-07-28T09:00:00Z",
            "windowFrom": "2026-07-01T00:00:00+01:00",
            "windowTo": "2026-09-01T00:00:00+01:00",
        },
        "events": events,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    lines = [",".join(header)] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_register(path: Path) -> Path:
    return _write_csv(
        path,
        ["type", "title", "owner", "due", "priority"],
        [
            ["action", "Fix widget", "Nonexistent Person", f"{TODAY}", "high"],
            ["commitment", "Send report", "", f"{TODAY}", "medium"],
            ["topic", "Discuss roadmap", "", "", ""],
        ],
    )


def _write_typeless(path: Path) -> Path:
    return _write_csv(path, ["title", "owner"], [["Task A", ""], ["Task B", ""]])


def _write_people(path: Path) -> Path:
    return _write_csv(
        path,
        ["name", "email", "team"],
        [["Jordan Lee", "jordan.lee@bank.com", "Audit"], ["Sam Patel", "sam.patel@bank.com", "Audit"]],
    )


def _write_default_fixture(kind: str, path: Path) -> None:
    if kind == "mail":
        _write_mailbox(path, [_msg("default-m1")])
    elif kind == "diary":
        _write_diary(path, [_event("2026-08-03T09:00:00Z")])
    elif kind == "people":
        _write_people(path)
    else:
        _write_register(path)


# --- each kind imports a small valid fixture and rows land ------------------


def test_mail_kind_imports_rows(tmp_path):
    mailbox = _write_mailbox(tmp_path / "mailbox.json", [_msg("m1"), _msg("m2", subject="Second")])
    db_path = tmp_path / "test.db"

    result = run_cli(["mail", mailbox], db_path)

    assert result.returncode == 0, result.stderr
    assert "mailbox.json: 2 added, 0 updated, 0 purged" in result.stdout
    rows = _query(db_path, "SELECT message_id FROM mail_message")
    assert {r["message_id"] for r in rows} == {"m1", "m2"}


def test_diary_kind_imports_rows(tmp_path):
    diary = _write_diary(tmp_path / "diary.json", [_event("2026-08-03T09:00:00Z")])
    db_path = tmp_path / "test.db"

    result = run_cli(["diary", diary], db_path)

    assert result.returncode == 0, result.stderr
    assert "diary.json: 1 added, 0 updated, 0 unchanged" in result.stdout
    rows = _query(db_path, "SELECT id FROM diary_event")
    assert len(rows) == 1


def test_register_kind_imports_all_types(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register], db_path)

    assert result.returncode == 0, result.stderr
    assert "1 action, 1 commitment, 1 topic created" in result.stdout
    assert _query(db_path, "SELECT title FROM action") == [{"title": "Fix widget"}]
    assert _query(db_path, "SELECT title FROM commitment") == [{"title": "Send report"}]
    assert _query(db_path, "SELECT title FROM topic") == [{"title": "Discuss roadmap"}]


def test_people_kind_imports_rows(tmp_path):
    people = _write_people(tmp_path / "people.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["people", people], db_path)

    assert result.returncode == 0, result.stderr
    assert "2 created" in result.stdout
    rows = _query(db_path, "SELECT name FROM person")
    assert {r["name"] for r in rows} == {"Jordan Lee", "Sam Patel"}


# --- dry-run writes nothing ---------------------------------------------------


@pytest.mark.parametrize("kind,writer", [("register", _write_register), ("people", _write_people)])
def test_dry_run_writes_nothing(tmp_path, kind, writer):
    fixture = writer(tmp_path / DEFAULT_FILES[kind])
    db_path = tmp_path / "test.db"

    result = run_cli([kind, fixture, "--dry-run"], db_path)

    assert result.returncode == 0, result.stderr
    table = {"register": "action", "people": "person"}[kind]
    assert _query(db_path, f"SELECT * FROM {table}") == []
    if kind == "register":
        assert _query(db_path, "SELECT * FROM commitment") == []
        assert _query(db_path, "SELECT * FROM topic") == []


def test_register_dry_run_reports_would_create(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--dry-run"], db_path)

    assert result.returncode == 0, result.stderr
    assert "would be created" in result.stdout
    assert _query(db_path, "SELECT * FROM action") == []


# --- friendly aliases set the right default type ------------------------------


def test_topics_alias_defaults_typeless_rows_to_topic(tmp_path):
    csv_path = _write_typeless(tmp_path / "notype.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["topics", csv_path], db_path)

    assert result.returncode == 0, result.stderr
    titles = {r["title"] for r in _query(db_path, "SELECT title FROM topic")}
    assert titles == {"Task A", "Task B"}
    assert _query(db_path, "SELECT * FROM action") == []
    assert _query(db_path, "SELECT * FROM commitment") == []


def test_actions_alias_defaults_typeless_rows_to_action(tmp_path):
    csv_path = _write_typeless(tmp_path / "notype.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["actions", csv_path], db_path)

    assert result.returncode == 0, result.stderr
    titles = {r["title"] for r in _query(db_path, "SELECT title FROM action")}
    assert titles == {"Task A", "Task B"}
    assert _query(db_path, "SELECT * FROM topic") == []


def test_commitments_alias_defaults_typeless_rows_to_commitment(tmp_path):
    csv_path = _write_typeless(tmp_path / "notype.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["commitments", csv_path], db_path)

    assert result.returncode == 0, result.stderr
    titles = {r["title"] for r in _query(db_path, "SELECT title FROM commitment")}
    assert titles == {"Task A", "Task B"}


# --- preview warnings surface in human output and --json ----------------------


def test_unmatched_owner_warning_appears_in_output(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register], db_path)

    assert result.returncode == 0, result.stderr
    assert "Nonexistent Person" in result.stdout
    assert "not found" in result.stdout


def test_unmatched_owner_warning_in_json_payload(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--json"], db_path)

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    entry = summary["files"][0]
    assert any("Nonexistent Person" in w for w in entry["warnings"])
    assert entry["skipped"] == 0


# --- --json shape for a CSV kind -----------------------------------------------


def test_json_shape_for_csv_kind(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--json"], db_path)

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert set(summary.keys()) == {"files", "totals"}
    assert len(summary["files"]) == 1
    entry = summary["files"][0]
    assert entry["path"] == str(register)
    for key in ("actions", "commitments", "topics", "skipped", "warnings"):
        assert key in entry
    assert entry["actions"] == 1
    assert entry["commitments"] == 1
    assert entry["topics"] == 1
    assert summary["totals"]["actions"] == 1
    assert summary["totals"]["commitments"] == 1
    assert summary["totals"]["topics"] == 1


# --- unknown kind exits 2 -------------------------------------------------------


def test_unknown_kind_exits_2(tmp_path):
    db_path = tmp_path / "test.db"
    result = run_cli(["frobnicate"], db_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() != ""


# --- malformed CSV exits 3 ------------------------------------------------------


def test_malformed_csv_missing_title_column_exits_3(tmp_path):
    bad = _write_csv(tmp_path / "register.csv", ["foo", "bar"], [["1", "2"]])
    db_path = tmp_path / "test.db"

    result = run_cli(["register", bad], db_path)

    assert result.returncode == 3
    assert result.stdout == ""
    assert "title" in result.stderr.lower()


# --- default-path resolution per kind -------------------------------------------


@pytest.mark.parametrize("kind", sorted(DEFAULT_FILES))
def test_default_path_with_no_argument(tmp_path, kind):
    default_path = REPO_ROOT / "data" / "imports" / DEFAULT_FILES[kind]
    if default_path.exists():
        # The scheduled extractor (or a previous manual import) may have dropped a
        # real file here (e.g. on the user's corporate machine); refusing to
        # overwrite it is correct, but that's an unrelated environment condition,
        # not a test failure.
        pytest.skip(f"{default_path} exists — skipping default-path test for {kind}")
    db_path = tmp_path / "test.db"
    _write_default_fixture(kind, default_path)
    try:
        result = run_cli([kind], db_path)
        assert result.returncode == 0, result.stderr
    finally:
        default_path.unlink(missing_ok=True)


# --- F1: duplicate ids are surfaced in the human-readable line ------------------


def test_mail_duplicate_ids_reported_in_human_line(tmp_path):
    mailbox = _write_mailbox(tmp_path / "mailbox.json", [_msg("dup1"), _msg("dup1", subject="Second")])
    db_path = tmp_path / "test.db"

    result = run_cli(["mail", mailbox], db_path)

    assert result.returncode == 0, result.stderr
    assert "1 duplicate ids collapsed" in result.stdout


def test_diary_duplicate_ids_reported_in_human_line(tmp_path):
    occurrence = "2026-08-03T09:00:00Z"
    diary = _write_diary(
        tmp_path / "diary.json",
        [_event(occurrence, subject="v1"), _event(occurrence, subject="v2")],
    )
    db_path = tmp_path / "test.db"

    result = run_cli(["diary", diary], db_path)

    assert result.returncode == 0, result.stderr
    assert "1 duplicate ids collapsed" in result.stdout


def test_mail_no_duplicates_line_omits_duplicate_clause(tmp_path):
    mailbox = _write_mailbox(tmp_path / "mailbox.json", [_msg("m1")])
    db_path = tmp_path / "test.db"

    result = run_cli(["mail", mailbox], db_path)

    assert result.returncode == 0, result.stderr
    assert "duplicate" not in result.stdout


# --- F2: --dry-run --archive must not archive the file --------------------------


def test_dry_run_archive_leaves_source_file_in_place(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--dry-run", "--archive"], db_path)

    assert result.returncode == 0, result.stderr
    assert register.exists()
    assert not (tmp_path / "archive").exists()
    assert _query(db_path, "SELECT * FROM action") == []


# --- F11: --archive on a normal (non-dry-run) run, and .xlsx routing ------------


def test_archive_moves_file_after_normal_csv_run(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--archive"], db_path)

    assert result.returncode == 0, result.stderr
    assert not register.exists()
    archived = list((tmp_path / "archive").glob("register.csv.*.csv"))
    assert len(archived) == 1
    assert _query(db_path, "SELECT title FROM action") == [{"title": "Fix widget"}]


def test_xlsx_routes_through_rows_from_xlsx(tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["type", "title", "owner", "due", "priority"])
    sheet.append(["action", "Ship the xlsx importer", "", TODAY, "medium"])
    xlsx_path = tmp_path / "register.xlsx"
    workbook.save(xlsx_path)
    db_path = tmp_path / "test.db"

    result = run_cli(["register", xlsx_path], db_path)

    assert result.returncode == 0, result.stderr
    assert "1 action" in result.stdout
    assert _query(db_path, "SELECT title FROM action") == [{"title": "Ship the xlsx importer"}]


# --- F5: --default-meeting-id validation and reporting --------------------------


def _seed_meeting(db_path: Path) -> int:
    """Create a Forum + Meeting directly in db_path (via a subprocess bound to that
    FULCRUM_DB) and return the new meeting's id, so a --default-meeting-id test has a
    real id to link against."""
    script = (
        "import sys; sys.path.insert(0, sys.argv[1] + '/backend')\n"
        "from datetime import datetime\n"
        "from app.db import SessionLocal, init_db\n"
        "from app.models import Forum, Meeting\n"
        "init_db()\n"
        "db = SessionLocal()\n"
        "forum = Forum(name='AET Weekly')\n"
        "db.add(forum)\n"
        "db.flush()\n"
        "meeting = Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 10, 0))\n"
        "db.add(meeting)\n"
        "db.commit()\n"
        "print(meeting.id)\n"
    )
    env = dict(os.environ)
    env["FULCRUM_DB"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def test_default_meeting_id_bad_id_exits_3(tmp_path):
    register = _write_register(tmp_path / "register.csv")
    db_path = tmp_path / "test.db"

    result = run_cli(["register", register, "--default-meeting-id", "999999"], db_path)

    assert result.returncode == 3
    assert "no meeting with id 999999" in result.stderr
    assert _query(db_path, "SELECT * FROM action") == []


def test_default_meeting_id_links_rows_and_reports_count(tmp_path):
    db_path = tmp_path / "test.db"
    meeting_id = _seed_meeting(db_path)
    register = _write_register(tmp_path / "register.csv")

    result = run_cli(["register", register, "--default-meeting-id", str(meeting_id)], db_path)

    assert result.returncode == 0, result.stderr
    assert "3 linked to meeting" in result.stdout
    links = _query(db_path, "SELECT from_id, to_type FROM link WHERE from_type = 'meeting'")
    assert len(links) == 3
    assert all(link["from_id"] == meeting_id for link in links)


# --- F6: malformed diary structure exits 3, not 1 -------------------------------


def test_diary_non_list_events_exits_3(tmp_path):
    path = tmp_path / "diary.json"
    path.write_text(json.dumps({"meta": {}, "events": {"not": "a list"}}), encoding="utf-8")
    db_path = tmp_path / "test.db"

    result = run_cli(["diary", path], db_path)

    assert result.returncode == 3
    assert "list" in result.stderr.lower()


def test_diary_non_dict_event_entry_exits_3(tmp_path):
    path = tmp_path / "diary.json"
    path.write_text(json.dumps({"meta": {}, "events": ["not-a-dict"]}), encoding="utf-8")
    db_path = tmp_path / "test.db"

    result = run_cli(["diary", path], db_path)

    assert result.returncode == 3
    assert "object" in result.stderr.lower()


def test_diary_list_valued_id_exits_3(tmp_path):
    path = tmp_path / "diary.json"
    path.write_text(
        json.dumps({"meta": {}, "events": [{**_event("2026-08-03T09:00:00Z"), "id": ["not", "a", "string"]}]}),
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"

    result = run_cli(["diary", path], db_path)

    assert result.returncode == 3
    assert "id" in result.stderr.lower()
