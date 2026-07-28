"""Import actions from an MS Planner export (Excel) or a generic CSV.

Planner's "Export plan to Excel" sheet has columns like:
Task Name, Bucket Name, Progress, Priority, Assigned To, Due Date, Description, ...
Generic CSV templates use lowercase snake_case headers.
"""

import csv
import io
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Action
from .quickadd import find_person, find_workstream

PROGRESS_MAP = {
    "not started": "todo",
    "in progress": "in_progress",
    "completed": "done",
}
PRIORITY_MAP = {
    "urgent": "high",
    "important": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

# canonical field -> accepted header spellings (lowercased)
HEADER_ALIASES = {
    "title": ["task name", "title", "name"],
    "description": ["description", "notes"],
    "owner": ["assigned to", "owner", "assignee"],
    "due": ["due date", "due", "due_date"],
    "status": ["progress", "status"],
    "priority": ["priority"],
    "workstream": ["bucket name", "workstream", "bucket"],
}


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y", "%d-%b-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _map_headers(headers: list[str]) -> dict[str, int]:
    """canonical field -> column index."""
    mapping: dict[str, int] = {}
    lowered = [h.strip().lower() for h in headers]
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field] = lowered.index(alias)
                break
    return mapping


def rows_from_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig")
    return [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]


def rows_from_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows = []
    for row in sheet.iter_rows(values_only=True):
        cells = ["" if cell is None else str(cell) for cell in row]
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    workbook.close()
    return rows


def preview_import(db: Session, rows: list[list[str]]) -> dict:
    """Parse rows into proposed actions without writing anything."""
    if not rows:
        return {"columns": {}, "items": [], "skipped": 0}
    mapping = _map_headers(rows[0])
    if "title" not in mapping:
        raise ValueError(
            "Could not find a title column (expected one of: "
            + ", ".join(HEADER_ALIASES["title"])
            + ")"
        )
    items, skipped = [], 0
    for row in rows[1:]:
        def cell(field: str) -> str:
            index = mapping.get(field)
            return row[index].strip() if index is not None and index < len(row) else ""

        title = cell("title")
        if not title:
            skipped += 1
            continue
        owner_name = cell("owner").split(";")[0].strip()
        owner = find_person(db, owner_name) if owner_name else None
        ws_name = cell("workstream")
        workstream = find_workstream(db, ws_name) if ws_name else None
        items.append(
            {
                "title": title,
                "description": cell("description") or None,
                "owner_id": owner.id if owner else None,
                "owner_name": owner.name if owner else (owner_name or None),
                "owner_matched": owner is not None or not owner_name,
                "workstream_id": workstream.id if workstream else None,
                "workstream_name": workstream.name if workstream else (ws_name or None),
                "due_date": (d := _parse_date(cell("due"))) and d.isoformat(),
                "status": PROGRESS_MAP.get(cell("status").lower(), "todo"),
                "priority": PRIORITY_MAP.get(cell("priority").lower(), "medium"),
            }
        )
    return {"columns": {k: rows[0][v] for k, v in mapping.items()}, "items": items, "skipped": skipped}


def commit_import(db: Session, items: list[dict]) -> int:
    created = 0
    for item in items:
        db.add(
            Action(
                title=item["title"],
                description=item.get("description"),
                owner_id=item.get("owner_id"),
                workstream_id=item.get("workstream_id"),
                due_date=date.fromisoformat(item["due_date"]) if item.get("due_date") else None,
                status=item.get("status", "todo"),
                priority=item.get("priority", "medium"),
            )
        )
        created += 1
    db.commit()
    return created


TEMPLATES = {
    "actions": ["title", "description", "owner", "workstream", "due", "status", "priority"],
    "commitments": ["title", "description", "owner", "workstream", "due", "origin", "priority"],
    "topics": ["title", "description", "intent", "duration_minutes", "owner", "workstream", "due"],
    "key_dates": ["title", "due", "kind", "hard", "workstream", "description"],
}


def template_csv(name: str) -> str:
    headers = TEMPLATES[name]
    return ",".join(headers) + "\n"
