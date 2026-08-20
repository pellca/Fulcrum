"""Bulk delete with reference checks.

The `link` table is polymorphic, so nothing at the database level cleans up edges
pointing at a deleted row — every delete path goes through here to prune them.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (
    Action,
    AgendaItem,
    Chase,
    Commitment,
    Decision,
    DiaryEvent,
    Forum,
    KeyDate,
    Link,
    Meeting,
    Person,
    PersonNote,
    Topic,
    Workstream,
)

DELETABLE = {
    "action": Action,
    "commitment": Commitment,
    "topic": Topic,
    "person": Person,
    "workstream": Workstream,
    "key_date": KeyDate,
    "decision": Decision,
    "forum": Forum,
    "meeting": Meeting,
    "diary_event": DiaryEvent,
}

LABELS = {
    "action": "actions",
    "commitment": "commitments",
    "topic": "topics",
    "person": "people",
    "workstream": "workstreams",
    "key_date": "key dates",
    "decision": "decisions",
    "forum": "forums",
    "meeting": "meetings",
    "diary_event": "diary events",
}


def prune_links(db: Session, entity_type: str, entity_ids: list) -> int:
    """Remove link edges pointing at any of these entities."""
    if not entity_ids:
        return 0
    removed = (
        db.query(Link)
        .filter(
            or_(
                (Link.from_type == entity_type) & (Link.from_id.in_(entity_ids)),
                (Link.to_type == entity_type) & (Link.to_id.in_(entity_ids)),
            )
        )
        .delete(synchronize_session=False)
    )
    return removed or 0


def _person_references(db: Session, person_ids: list[int]) -> list[dict]:
    """What loses its owner if these people go. Ordered most-consequential first."""
    checks = [
        ("open actions owned", db.query(Action).filter(
            Action.owner_id.in_(person_ids), Action.status.notin_(["done", "cancelled"]))),
        ("open commitments owned", db.query(Commitment).filter(
            Commitment.owner_id.in_(person_ids), Commitment.status.notin_(["delivered", "dropped"]))),
        ("closed items owned", db.query(Action).filter(
            Action.owner_id.in_(person_ids), Action.status.in_(["done", "cancelled"]))),
        ("topics sponsored", db.query(Topic).filter(Topic.sponsor_id.in_(person_ids))),
        ("forums chaired", db.query(Forum).filter(Forum.chair_id.in_(person_ids))),
        ("decisions owned", db.query(Decision).filter(Decision.owner_id.in_(person_ids))),
        ("workstreams owned", db.query(Workstream).filter(Workstream.owner_id.in_(person_ids))),
        ("notes recorded", db.query(PersonNote).filter(PersonNote.person_id.in_(person_ids))),
    ]
    findings = []
    for label, query in checks:
        rows = query.limit(6).all()
        count = query.count()
        if count:
            findings.append(
                {
                    "label": label,
                    "count": count,
                    "examples": [
                        (getattr(r, "title", None) or getattr(r, "name", None) or getattr(r, "note", ""))[:80]
                        for r in rows
                    ],
                }
            )
    return findings


def _meeting_cascade_warnings(db: Session, meeting_ids: list) -> list[dict]:
    """Agenda items and decisions that these meetings take with them."""
    warnings: list[dict] = []
    if not meeting_ids:
        return warnings
    agenda = db.query(AgendaItem).filter(AgendaItem.meeting_id.in_(meeting_ids))
    if agenda.count():
        warnings.append(
            {
                "label": "agenda items that will be removed",
                "count": agenda.count(),
                "examples": [a.topic.title for a in agenda.limit(6)],
            }
        )
    decisions = db.query(Decision).filter(Decision.meeting_id.in_(meeting_ids))
    if decisions.count():
        warnings.append(
            {
                "label": "decisions that will lose their meeting",
                "count": decisions.count(),
                "examples": [d.title for d in decisions.limit(6)],
            }
        )
    return warnings


def check_references(db: Session, entity_type: str, ids: list) -> dict:
    """Preflight: what a delete would affect. Never mutates anything."""
    model = DELETABLE.get(entity_type)
    if model is None:
        raise ValueError(f"Cannot delete '{entity_type}'")
    rows = db.query(model).filter(model.id.in_(ids)).all()
    found_ids = [r.id for r in rows]

    warnings: list[dict] = []
    if entity_type == "person" and found_ids:
        warnings = _person_references(db, found_ids)
    elif entity_type == "commitment" and found_ids:
        child_actions = db.query(Action).filter(Action.commitment_id.in_(found_ids))
        if child_actions.count():
            warnings.append(
                {
                    "label": "delivery actions attached",
                    "count": child_actions.count(),
                    "examples": [a.title for a in child_actions.limit(6)],
                }
            )
    elif entity_type == "forum" and found_ids:
        meetings = db.query(Meeting).filter(Meeting.forum_id.in_(found_ids))
        meeting_count = meetings.count()
        if meeting_count:
            meeting_rows = meetings.limit(6).all()
            warnings.append(
                {
                    "label": "meetings that will be deleted with it",
                    "count": meeting_count,
                    "examples": [f"{m.forum.name} — {m.scheduled_at:%d %b %Y}" for m in meeting_rows],
                }
            )
            meeting_ids = [m.id for m in db.query(Meeting.id).filter(Meeting.forum_id.in_(found_ids)).all()]
            warnings.extend(_meeting_cascade_warnings(db, meeting_ids))
    elif entity_type == "topic" and found_ids:
        agenda = db.query(AgendaItem).filter(AgendaItem.topic_id.in_(found_ids))
        if agenda.count():
            warnings.append(
                {
                    "label": "agenda slots it will be removed from",
                    "count": agenda.count(),
                    "examples": [
                        f"{a.meeting.forum.name} — {a.meeting.scheduled_at:%d %b %Y}" for a in agenda.limit(6)
                    ],
                }
            )
    elif entity_type == "meeting" and found_ids:
        warnings.extend(_meeting_cascade_warnings(db, found_ids))
    elif entity_type == "diary_event" and found_ids:
        meetings = db.query(Meeting).filter(Meeting.diary_event_id.in_(found_ids))
        if meetings.count():
            warnings.append(
                {
                    "label": "meetings that will be unlinked",
                    "count": meetings.count(),
                    "examples": [
                        f"{m.forum.name} — {m.scheduled_at:%d %b %Y}" for m in meetings.limit(6)
                    ],
                }
            )

    link_count = (
        db.query(Link)
        .filter(
            or_(
                (Link.from_type == entity_type) & (Link.from_id.in_(found_ids)),
                (Link.to_type == entity_type) & (Link.to_id.in_(found_ids)),
            )
        )
        .count()
        if found_ids
        else 0
    )
    if link_count:
        warnings.append({"label": "links that will be removed", "count": link_count, "examples": []})

    if entity_type in ("action", "commitment") and found_ids:
        column = Chase.action_id if entity_type == "action" else Chase.commitment_id
        chase_count = db.query(Chase).filter(column.in_(found_ids)).count()
        if chase_count:
            warnings.append(
                {"label": "chase history entries that will be lost", "count": chase_count, "examples": []}
            )

    def _title(r):
        if entity_type == "diary_event":
            return f"{r.start_date} {r.start_time} — {r.subject}"
        return (
            getattr(r, "title", None)
            or getattr(r, "name", None)
            or getattr(r, "subject", None)
            or str(r.id)
        )

    return {
        "type": entity_type,
        "label": LABELS.get(entity_type, entity_type),
        "requested": len(ids),
        "found": len(found_ids),
        "titles": [_title(r) for r in rows[:20]],
        "warnings": warnings,
    }


def delete_entities(db: Session, entity_type: str, ids: list) -> dict:
    model = DELETABLE.get(entity_type)
    if model is None:
        raise ValueError(f"Cannot delete '{entity_type}'")
    rows = db.query(model).filter(model.id.in_(ids)).all()
    found_ids = [r.id for r in rows]
    links_removed = prune_links(db, entity_type, found_ids)
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows), "links_removed": links_removed}
