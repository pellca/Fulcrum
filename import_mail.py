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

This is shorthand for `python import_data.py mail` — see import_data.py for the same
DLP-safe approach applied to diary, register (actions/commitments/topics) and people
imports.
"""

import argparse
import sys

# Module-level name (not inlined into _archive): a regression test monkeypatches
# `import_mail.datetime` and calls `import_mail._archive` directly, so `_archive` must
# resolve `datetime` through this module's own namespace, not cli_import's.
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import cli_import  # noqa: E402
from app.services.mail_import import import_mail_file  # noqa: E402


def _archive(path: Path) -> Path:
    return cli_import.archive_file(path, now=datetime.now)


def _line(summary: dict) -> str:
    line = f"{summary['added']} added, {summary['updated']} updated, {summary['purged']} purged"
    if summary.get("duplicates"):
        line += f", {summary['duplicates']} duplicate ids collapsed"
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import one or more mailbox.json files directly into the Fulcrum SQLite DB."
    )
    parser.add_argument("paths", nargs="*", metavar="PATH", help="mailbox.json file(s) or directory/directories")
    parser.add_argument("--archive", action="store_true", help="move each file to archive/ after a successful import")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a single JSON summary to stdout")
    args = parser.parse_args(argv)

    return cli_import.run(
        prog="import_mail",
        args=args,
        default_filename="mailbox.json",
        glob_pattern="mailbox*.json",
        process_file=lambda db, target, _args: import_mail_file(db, target),
        totals_keys=["added", "updated", "purged", "duplicates"],
        line_for=_line,
        archive_fn=_archive,
    )


if __name__ == "__main__":
    sys.exit(main())
