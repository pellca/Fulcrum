"""Import a diary.json produced by OutlookDiaryExtractor.

The extractor guarantees: event `id` = `<GlobalAppointmentID>|<occurrenceStartUtc>`,
status is `active`/`cancelled`, and a reschedule appears as a cancelled entry at the
old slot plus an active entry at the new one, sharing the GlobalAppointmentID prefix.
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import DiaryEvent, Meeting, Person, PersonAlias
from .import_utils import dedupe_by_id


def _prefix(event_id: str) -> str:
    return event_id.split("|", 1)[0]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def import_diary_file(db: Session, path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "events" not in payload:
        raise ValueError("Not a diary.json file: missing 'events' key")
    events_raw = payload["events"]
    if not isinstance(events_raw, list):
        raise ValueError("Not a diary.json file: 'events' must be a list")
    for raw in events_raw:
        if not isinstance(raw, dict):
            raise ValueError(f"Malformed event entry: expected an object, got {type(raw).__name__}")
        event_id = raw.get("id")
        if event_id is not None and not isinstance(event_id, (str, int)):
            # A list/dict-valued id would otherwise reach db.get(DiaryEvent, event_id)
            # (a single-column primary key lookup) and blow up with an opaque
            # sqlalchemy.exc.InvalidRequestError instead of a clean exit 3.
            raise ValueError(f"Malformed event entry: 'id' must be a string, got {type(event_id).__name__}")

    events, duplicates = dedupe_by_id(events_raw)

    counts = {"added": 0, "updated": 0, "unchanged": 0}
    for raw in events:
        event_id = raw.get("id")
        if not event_id:
            continue
        row = db.get(DiaryEvent, event_id)
        fields = dict(
            subject=raw.get("subject"),
            start=raw.get("start"),
            end=raw.get("end"),
            start_date=raw.get("startDate"),
            start_time=raw.get("startTime"),
            end_date=raw.get("endDate"),
            end_time=raw.get("endTime"),
            organizer=raw.get("organizer"),
            required_attendees=raw.get("requiredAttendees") or [],
            optional_attendees=raw.get("optionalAttendees") or [],
            location=raw.get("location"),
            categories=raw.get("categories") or [],
            is_recurring=bool(raw.get("isRecurring")),
            is_all_day=bool(raw.get("isAllDay")),
            status=raw.get("status") or "active",
            last_modified=raw.get("lastModified"),
            cancelled_at=raw.get("cancelledAt"),
            description=raw.get("description"),
            raw=raw,
        )
        if row is None:
            db.add(DiaryEvent(id=event_id, **fields))
            counts["added"] += 1
        elif row.last_modified != fields["last_modified"] or row.status != fields["status"]:
            for key, value in fields.items():
                setattr(row, key, value)
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    db.flush()

    moved = _detect_reschedules(db)
    meetings_followed = _follow_moved_meetings(db)
    unmatched = unmatched_attendees(db)
    db.commit()

    meta = payload.get("meta", {})
    return {
        **counts,
        "duplicates": duplicates,
        "moved_pairs": moved,
        "meetings_updated": meetings_followed,
        "unmatched_attendees": unmatched,
        "mailbox": meta.get("mailbox"),
        "window_from": meta.get("windowFrom"),
        "window_to": meta.get("windowTo"),
    }


def _detect_reschedules(db: Session) -> int:
    """Pair cancelled occurrences with an active sibling sharing the appointment id."""
    cancelled = (
        db.query(DiaryEvent)
        .filter(DiaryEvent.status == "cancelled", DiaryEvent.moved_to_event_id.is_(None))
        .all()
    )
    if not cancelled:
        return 0
    active = db.query(DiaryEvent).filter(DiaryEvent.status == "active").all()
    active_by_prefix: dict[str, list[DiaryEvent]] = {}
    for event in active:
        active_by_prefix.setdefault(_prefix(event.id), []).append(event)

    moved = 0
    for old in cancelled:
        siblings = [e for e in active_by_prefix.get(_prefix(old.id), []) if e.id != old.id]
        if not siblings:
            continue
        # nearest new occurrence to the old slot is the most plausible replacement
        old_start = _parse_iso(old.start)
        if old_start is not None:
            siblings.sort(
                key=lambda e: abs((_parse_iso(e.start) - old_start).total_seconds())
                if _parse_iso(e.start)
                else float("inf")
            )
        old.moved_to_event_id = siblings[0].id
        moved += 1
    return moved


def _follow_moved_meetings(db: Session) -> int:
    """Meetings linked to a cancelled+moved diary event follow it to the new slot."""
    updated = 0
    meetings = db.query(Meeting).filter(Meeting.diary_event_id.isnot(None)).all()
    for meeting in meetings:
        event = db.get(DiaryEvent, meeting.diary_event_id)
        if event is None or event.status != "cancelled" or not event.moved_to_event_id:
            continue
        replacement = db.get(DiaryEvent, event.moved_to_event_id)
        if replacement is None:
            continue
        new_start = _parse_iso(replacement.start)
        if new_start is not None:
            meeting.scheduled_at = new_start.replace(tzinfo=None)
        meeting.diary_event_id = replacement.id
        meeting.needs_review = True
        updated += 1
    return updated


def unmatched_attendees(db: Session, limit: int = 100) -> list[str]:
    """Display names appearing in diary events with no Person or alias match."""
    known = {name.lower() for (name,) in db.query(func.lower(Person.name)).all()}
    known |= {alias.lower() for (alias,) in db.query(func.lower(PersonAlias.alias)).all()}

    seen: dict[str, None] = {}
    for event in db.query(DiaryEvent).filter(DiaryEvent.status == "active").all():
        for name in (event.required_attendees or []) + (event.optional_attendees or []):
            cleaned = name.strip()
            if cleaned and cleaned.lower() not in known:
                seen.setdefault(cleaned)
    return sorted(seen)[:limit]
