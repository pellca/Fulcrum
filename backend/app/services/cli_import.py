"""Shared machinery for the scripted (non-browser) import CLIs — WP-5.1 built this for
`import_mail.py` so mailbox content never travels through an HTTP request the bank's
DLP inspection could see; WP-6.2 generalised it so every importer (mail, diary, the
CSV/XLSX action/commitment/topic register, and people) gets the same DLP-safe path.

This module owns the parts that are identical across every kind of import:
    - resolving PATH arguments (explicit files, a directory glob, or a per-kind
      default filename under `config.IMPORTS_DIR`)
    - `init_db()` and a fresh `SessionLocal()` per file
    - the `--archive` / `--quiet` / `--json` flags
    - the human-readable per-file line + `Total: ... across N files` summary, and the
      single-line `--json` summary
    - the exit-code contract: 0 ok, 1 unexpected error, 2 not found, 3 malformed input,
      4 DB locked/OperationalError (with the friendly "retry in a moment" message)

What differs between kinds — how a file actually gets imported, and how one file's
result renders as a line of text — is supplied by the caller as plain callables, so
this module has no knowledge of mailboxes, diaries, actions, or people.
"""

import argparse
import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..config import IMPORTS_DIR
from ..db import SessionLocal, init_db

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_NOT_FOUND = 2
EXIT_MALFORMED = 3
EXIT_DB_ERROR = 4


class TargetError(Exception):
    """A PATH argument could not be resolved to any file to import."""


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """paths + --archive/--quiet/--json, shared by every kind."""
    parser.add_argument("paths", nargs="*", metavar="PATH", help="file(s) or directory/directories to import")
    parser.add_argument("--archive", action="store_true", help="move each file to archive/ after a successful import")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a single JSON summary to stdout")


def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run", action="store_true", help="run the preview only and print what would be created; write nothing"
    )


def add_default_meeting_id_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--default-meeting-id",
        type=int,
        default=None,
        help="meeting id to link rows to when a row's own meeting reference doesn't match one",
    )


def resolve_targets(paths: list[str], default_filename: str, glob_pattern: str) -> list[Path]:
    if not paths:
        paths = [str(IMPORTS_DIR / default_filename)]

    targets: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_dir():
            matches = sorted(candidate.glob(glob_pattern))
            if not matches:
                raise TargetError(f"no {glob_pattern} files found in {candidate}")
            targets.extend(matches)
        elif candidate.is_file():
            targets.append(candidate)
        else:
            raise TargetError(f"file not found: {candidate}")
    return targets


def archive_file(path: Path, *, now: Callable[[], datetime] | None = None) -> Path:
    """Move `path` into a sibling archive/ dir, timestamped, de-duplicating same-second
    collisions. `now` is injectable so a caller (e.g. import_mail.py, for its frozen-
    clock regression test) can control the clock without this module knowing about it.
    """
    now = now or datetime.now
    archive_dir = path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    suffix = path.suffix
    destination = archive_dir / f"{path.name}.{stamp}{suffix}"
    n = 1
    while destination.exists():
        destination = archive_dir / f"{path.name}.{stamp}-{n}{suffix}"
        n += 1
    path.rename(destination)
    return destination


def report_db_error(prog: str, exc: OperationalError) -> int:
    if "locked" in str(exc).lower():
        print(
            f"{prog}: database is locked — Fulcrum may be mid-write, retry in a moment.",
            file=sys.stderr,
        )
    else:
        print(f"{prog}: database error: {exc}", file=sys.stderr)
    return EXIT_DB_ERROR


def emit(args: argparse.Namespace, files: list[dict], totals: dict, line_for: Callable[[dict], str]) -> None:
    if args.as_json:
        print(json.dumps({"files": files, "totals": totals}))
    elif not args.quiet and len(files) > 1:
        print(f"Total: {line_for(totals)} across {len(files)} files")


def run(
    *,
    prog: str,
    args: argparse.Namespace,
    default_filename: str,
    glob_pattern: str,
    process_file: Callable[[Session, Path, argparse.Namespace], dict],
    totals_keys: list[str],
    line_for: Callable[[dict], str],
    archive_fn: Callable[[Path], Path] | None = None,
) -> int:
    """Drive the whole import: resolve targets, init the DB, import each file through
    `process_file`, archive on success, print per-file lines/warnings, and emit the
    JSON/summary. `process_file(db, path, args) -> dict` does the kind-specific work
    and raises FileNotFoundError / ValueError / json.JSONDecodeError / OperationalError
    to signal the corresponding exit code; anything else is EXIT_UNEXPECTED.

    The returned dict's numeric fields named in `totals_keys` are summed into the run
    totals; an optional "warnings" list of strings is printed (human mode) under the
    file's line and passed straight through into the JSON entry so preview warnings and
    skipped rows are never silently dropped.
    """
    archive_fn = archive_fn or archive_file

    try:
        targets = resolve_targets(args.paths, default_filename, glob_pattern)
    except TargetError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return EXIT_NOT_FOUND

    try:
        init_db()
    except OperationalError as exc:
        return report_db_error(prog, exc)
    except Exception as exc:  # noqa: BLE001
        print(f"{prog}: unexpected error initializing the database: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED

    files: list[dict] = []
    totals = dict.fromkeys(totals_keys, 0)

    for target in targets:
        db = SessionLocal()
        try:
            result = process_file(db, target, args)
        except FileNotFoundError:
            db.close()
            print(f"{prog}: file not found: {target}", file=sys.stderr)
            emit(args, files, totals, line_for)
            return EXIT_NOT_FOUND
        except (ValueError, json.JSONDecodeError) as exc:
            db.close()
            print(f"{prog}: {target}: malformed input: {exc}", file=sys.stderr)
            emit(args, files, totals, line_for)
            return EXIT_MALFORMED
        except OperationalError as exc:
            db.close()
            code = report_db_error(prog, exc)
            emit(args, files, totals, line_for)
            return code
        except Exception as exc:  # noqa: BLE001
            db.close()
            print(f"{prog}: {target}: unexpected error: {exc}", file=sys.stderr)
            emit(args, files, totals, line_for)
            return EXIT_UNEXPECTED
        else:
            db.close()

        if args.archive and not getattr(args, "dry_run", False):
            try:
                archive_fn(target)
            except OSError as exc:
                print(f"{prog}: {target}: imported but could not archive: {exc}", file=sys.stderr)

        entry = {"path": str(target), **result}
        files.append(entry)
        for key in totals:
            if key in result:
                totals[key] += result[key]

        if not args.quiet and not args.as_json:
            print(f"{target.name}: {line_for(result)}")
            for warning in result.get("warnings", []):
                print(f"  ! {warning}")

    emit(args, files, totals, line_for)
    return EXIT_OK
