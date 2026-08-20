"""Bulk-delete DiaryEvents by date range (retention / re-import cleanup).

Distinct from services/bulk.py's generic delete-by-ids: this operates on a
date range instead of an id list, and reports meetings-unlinked rather than
flagging needs_review, since "the diary moved and we auto-followed" (see
diary_import.py) is a different event from "the diary window fell out of
retention".
"""

from sqlalchemy.orm import Session

from ..models import DiaryEvent, Meeting
from .bulk import prune_links


def _events_query(db: Session, from_date: str, to_date: str, include_cancelled: bool):
    query = db.query(DiaryEvent).filter(
        DiaryEvent.start_date >= from_date, DiaryEvent.start_date <= to_date
    )
    if not include_cancelled:
        query = query.filter(DiaryEvent.status != "cancelled")
    return query


def purge_diary_range(
    db: Session, from_date: str, to_date: str, include_cancelled: bool, dry_run: bool
) -> dict:
    events = _events_query(db, from_date, to_date, include_cancelled).order_by(DiaryEvent.start_date).all()
    event_ids = [e.id for e in events]

    linked_meetings = (
        db.query(Meeting).filter(Meeting.diary_event_id.in_(event_ids)).all() if event_ids else []
    )

    if dry_run:
        return {
            "events": len(events),
            "linked_meetings": len(linked_meetings),
            "examples": [f"{e.start_date} {e.start_time} — {e.subject}" for e in events[:10]],
            "meeting_examples": [
                f"{m.forum.name} — {m.scheduled_at:%d %b %Y}" for m in linked_meetings[:10]
            ],
        }

    if not event_ids:
        return {"deleted": 0, "meetings_unlinked": 0}

    meetings_unlinked = (
        db.query(Meeting)
        .filter(Meeting.diary_event_id.in_(event_ids))
        .update({"diary_event_id": None}, synchronize_session=False)
    )
    # Defensive: Link.from_id/to_id are integer columns while DiaryEvent.id is
    # a string, so no code path can create a real diary_event link today (see
    # CLAUDE.md's "anything linkable needs an integer primary key" rule). Still
    # prune any that exist rather than reporting a count nothing can produce.
    prune_links(db, "diary_event", event_ids)
    deleted = (
        db.query(DiaryEvent).filter(DiaryEvent.id.in_(event_ids)).delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted, "meetings_unlinked": meetings_unlinked}
