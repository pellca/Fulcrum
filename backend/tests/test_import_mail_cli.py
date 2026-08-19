"""Tests for the root-level `import_mail.py` CLI (WP-5.1): a DLP-safe way to load
mailbox.json straight into SQLite without going through the browser/API.

Invoked via subprocess (not imported) so each test gets its own process with its own
FULCRUM_DB override — the script binds SQLAlchemy's engine to config.DB_PATH at import
time, which would otherwise collide with the shared engine `conftest.py` already bound
for the rest of the suite. Every test points FULCRUM_DB at a tmp_path database; none
ever touch data/fulcrum.db.
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
SCRIPT = REPO_ROOT / "import_mail.py"

TODAY = date.today().isoformat()


def _msg(msg_id, subject="Subject", received_at=None, **overrides):
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
        "received_at": received_at or f"{TODAY}T09:00:00Z",
        "body_text": "Body text",
        "has_attachments": False,
    }
    base.update(overrides)
    return base


def _mailbox(messages, version=1):
    return {
        "meta": {
            "generated_at": f"{TODAY}T09:00:00Z",
            "mailbox": "delegate@bank.com",
            "window_days": 5,
            "tool": "export_mail",
            "version": version,
            "skipped": 0,
        },
        "messages": messages,
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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


def _rows(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT message_id, subject FROM mail_message").fetchall()]
    finally:
        conn.close()


def test_import_valid_sample_counts_and_rows(tmp_path):
    mailbox = _write(tmp_path / "mailbox.json", _mailbox([_msg("m1"), _msg("m2", subject="Second")]))
    db_path = tmp_path / "test.db"

    result = run_cli([mailbox], db_path)

    assert result.returncode == 0, result.stderr
    assert "mailbox.json: 2 added, 0 updated, 0 purged" in result.stdout

    rows = _rows(db_path)
    assert {r["message_id"] for r in rows} == {"m1", "m2"}
    assert {r["subject"] for r in rows} == {"Subject", "Second"}


def test_reimport_is_idempotent_reports_updated(tmp_path):
    mailbox = _write(tmp_path / "mailbox.json", _mailbox([_msg("m1")]))
    db_path = tmp_path / "test.db"

    first = run_cli([mailbox, "--json"], db_path)
    assert first.returncode == 0, first.stderr
    first_summary = json.loads(first.stdout)
    assert first_summary["totals"] == {"added": 1, "updated": 0, "purged": 0}

    second = run_cli([mailbox, "--json"], db_path)
    assert second.returncode == 0, second.stderr
    second_summary = json.loads(second.stdout)
    assert second_summary["totals"] == {"added": 0, "updated": 1, "purged": 0}

    assert len(_rows(db_path)) == 1


def test_default_path_with_no_argument(tmp_path):
    default_path = REPO_ROOT / "data" / "imports" / "mailbox.json"
    if default_path.exists():
        # The scheduled extractor may have dropped a real mailbox.json here (e.g. on the
        # user's corporate machine); refusing to overwrite it is correct, but that's an
        # unrelated environment condition, not a test failure.
        pytest.skip(f"{default_path} exists — skipping default-path test")
    db_path = tmp_path / "test.db"
    _write(default_path, _mailbox([_msg("default-m1")]))
    created_by_test = True
    try:
        result = run_cli([], db_path)
        assert result.returncode == 0, result.stderr
        assert "mailbox.json: 1 added, 0 updated, 0 purged" in result.stdout
        assert {r["message_id"] for r in _rows(db_path)} == {"default-m1"}
    finally:
        if created_by_test:
            default_path.unlink(missing_ok=True)


def test_directory_argument_imports_multiple_files_sorted(tmp_path):
    mail_dir = tmp_path / "mail"
    mail_dir.mkdir()
    _write(mail_dir / "mailbox-a.json", _mailbox([_msg("dir-m1")]))
    _write(mail_dir / "mailbox-b.json", _mailbox([_msg("dir-m2")]))
    _write(mail_dir / "not-mailbox.json", _mailbox([_msg("should-not-import")]))
    db_path = tmp_path / "test.db"

    result = run_cli([mail_dir, "--json"], db_path)

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    imported_names = [Path(f["path"]).name for f in summary["files"]]
    assert imported_names == ["mailbox-a.json", "mailbox-b.json"]
    assert summary["totals"] == {"added": 2, "updated": 0, "purged": 0}
    assert {r["message_id"] for r in _rows(db_path)} == {"dir-m1", "dir-m2"}


def test_missing_path_exits_2(tmp_path):
    db_path = tmp_path / "test.db"
    result = run_cli([tmp_path / "does-not-exist.json"], db_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "not found" in result.stderr.lower()


def test_malformed_json_syntax_exits_3(tmp_path):
    bad = tmp_path / "mailbox.json"
    bad.write_text("{not valid json", encoding="utf-8")
    db_path = tmp_path / "test.db"

    result = run_cli([bad], db_path)

    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr.strip() != ""


def test_malformed_contract_exits_3(tmp_path):
    bad = _write(tmp_path / "mailbox.json", {"foo": "bar"})
    db_path = tmp_path / "test.db"

    result = run_cli([bad], db_path)

    assert result.returncode == 3
    assert "messages" in result.stderr


def test_json_output_shape_and_totals(tmp_path):
    file_a = _write(tmp_path / "mailbox-a.json", _mailbox([_msg("json-m1"), _msg("json-m2")]))
    file_b = _write(tmp_path / "mailbox-b.json", _mailbox([_msg("json-m3")]))
    db_path = tmp_path / "test.db"

    result = run_cli([file_a, file_b, "--json"], db_path)

    assert result.returncode == 0, result.stderr
    # --json suppresses the human-readable lines entirely
    assert result.stdout.count("\n") <= 1
    summary = json.loads(result.stdout)
    assert set(summary.keys()) == {"files", "totals"}
    assert len(summary["files"]) == 2
    for entry in summary["files"]:
        assert set(entry.keys()) == {"path", "added", "updated", "purged"}
    assert summary["totals"] == {"added": 3, "updated": 0, "purged": 0}


def test_archive_moves_file_after_success(tmp_path):
    mailbox = _write(tmp_path / "mailbox.json", _mailbox([_msg("archive-m1")]))
    db_path = tmp_path / "test.db"

    result = run_cli([mailbox, "--archive"], db_path)

    assert result.returncode == 0, result.stderr
    assert not mailbox.exists()
    archive_dir = tmp_path / "archive"
    assert archive_dir.is_dir()
    archived = list(archive_dir.glob("mailbox.json.*.json"))
    assert len(archived) == 1


def test_archive_does_not_move_file_on_failure(tmp_path):
    bad = tmp_path / "mailbox.json"
    bad.write_text("{not valid json", encoding="utf-8")
    db_path = tmp_path / "test.db"

    result = run_cli([bad, "--archive"], db_path)

    assert result.returncode == 3
    assert bad.exists()
    assert not (tmp_path / "archive").exists()


def test_quiet_prints_nothing_on_success(tmp_path):
    mailbox = _write(tmp_path / "mailbox.json", _mailbox([_msg("quiet-m1")]))
    db_path = tmp_path / "test.db"

    result = run_cli([mailbox, "--quiet"], db_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert {r["message_id"] for r in _rows(db_path)} == {"quiet-m1"}


def test_json_and_quiet_together_still_emits_json(tmp_path):
    """F1 regression: --json --quiet used to print nothing because the --quiet guard
    returned before the JSON block ran."""
    mailbox = _write(tmp_path / "mailbox.json", _mailbox([_msg("jq-m1")]))
    db_path = tmp_path / "test.db"

    result = run_cli([mailbox, "--json", "--quiet"], db_path)

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["totals"] == {"added": 1, "updated": 0, "purged": 0}
    assert {r["message_id"] for r in _rows(db_path)} == {"jq-m1"}


def test_json_partial_summary_on_mid_batch_failure(tmp_path):
    """F2 regression: a mid-batch failure with --json must still report the files that
    already committed before the failing one, not emit nothing."""
    mail_dir = tmp_path / "mail"
    mail_dir.mkdir()
    _write(mail_dir / "mailbox-a.json", _mailbox([_msg("partial-m1")]))
    (mail_dir / "mailbox-b.json").write_text("{not valid json", encoding="utf-8")
    db_path = tmp_path / "test.db"

    result = run_cli([mail_dir, "--json"], db_path)

    assert result.returncode == 3
    summary = json.loads(result.stdout)
    assert len(summary["files"]) == 1
    assert Path(summary["files"][0]["path"]).name == "mailbox-a.json"
    assert summary["totals"] == {"added": 1, "updated": 0, "purged": 0}
    assert {r["message_id"] for r in _rows(db_path)} == {"partial-m1"}


def test_archive_same_second_collision_produces_distinct_files(tmp_path):
    """F5 regression: two archives within the same second must not silently overwrite
    each other. Freezes import_mail's clock so both _archive() calls compute the same
    timestamp, forcing the de-dup branch."""
    source = tmp_path / "mailbox.json"
    source.write_text("{}", encoding="utf-8")

    script = tmp_path / "freeze_archive.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import datetime as _dt\n"
        "\n"
        "class _Frozen(_dt.datetime):\n"
        "    @classmethod\n"
        "    def now(cls, tz=None):\n"
        "        return _dt.datetime(2026, 1, 1, 12, 0, 0)\n"
        "\n"
        "import import_mail\n"
        "import_mail.datetime = _Frozen\n"
        "from pathlib import Path\n"
        f"p = Path({str(source)!r})\n"
        "d1 = import_mail._archive(p)\n"
        "p.write_text('{}', encoding='utf-8')\n"
        "d2 = import_mail._archive(p)\n"
        "print(d1)\n"
        "print(d2)\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["FULCRUM_DB"] = str(tmp_path / "test.db")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2
    d1, d2 = Path(lines[0]), Path(lines[1])
    assert d1 != d2
    assert d1.exists()
    assert d2.exists()
    assert d2.name.endswith("-1.json")


@pytest.mark.skipif(sys.platform == "win32", reason="os.mkfifo is not available on Windows")
def test_fifo_path_exits_2_instead_of_hanging(tmp_path):
    """F12 regression: a non-regular-file path (FIFO here, but also device nodes etc.)
    must fall into the not-found branch rather than being opened and blocking forever."""
    fifo_path = tmp_path / "mailbox.json"
    os.mkfifo(fifo_path)
    db_path = tmp_path / "test.db"

    result = run_cli([fifo_path], db_path)

    assert result.returncode == 2
    assert "not found" in result.stderr.lower()
