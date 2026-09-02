from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Action,
    Chase,
    Commitment,
    Decision,
    DiaryEvent,
    DiscussionPoint,
    Forum,
    KeyDate,
    Meeting,
    Person,
    Topic,
    Workstream,
)

router = APIRouter(tags=["search"])

PER_TYPE_LIMIT = 8


def _snippet(text: str | None, query: str, width: int = 70) -> str | None:
    if not text:
        return None
    index = text.lower().find(query.lower())
    if index == -1:
        return None
    start = max(0, index - width // 2)
    end = min(len(text), index + len(query) + width // 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/search")
def global_search(q: str, db: Session = Depends(get_db)):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "Query must be at least 2 characters")
    like = _like(query)
    ilike = lambda col: col.ilike(like, escape="\\")  # noqa: E731
    results: list[dict] = []

    def add(kind: str, item_id, title: str, url: str, meta: str | None = None, snippet: str | None = None):
        results.append(
            {"type": kind, "id": item_id, "title": title, "url": url, "meta": meta, "snippet": snippet}
        )

    for person in (
        db.query(Person)
        .filter(or_(ilike(Person.name), ilike(Person.role), ilike(Person.team), ilike(Person.email)))
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "person",
            person.id,
            person.name,
            f"/people/{person.id}/pack",
            meta=" · ".join(filter(None, [person.role, person.team])),
        )

    for point in (
        db.query(DiscussionPoint)
        .filter(or_(ilike(DiscussionPoint.title), ilike(DiscussionPoint.detail)))
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "discussion_point",
            point.id,
            point.title,
            f"/people/{point.person_id}/pack",
            meta=" · ".join(filter(None, [point.status, point.person.name if point.person else None])),
            snippet=_snippet(point.detail, query),
        )

    for action in (
        db.query(Action)
        .filter(or_(ilike(Action.title), ilike(Action.description), ilike(Action.notes)))
        .order_by(Action.status.in_(["done", "cancelled"]), Action.due_date.is_(None), Action.due_date)
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "action",
            action.id,
            action.title,
            f"/register?open=action-{action.id}",
            meta=" · ".join(
                filter(None, [action.status.replace("_", " "), action.owner.name if action.owner else None,
                              f"due {action.due_date.isoformat()}" if action.due_date else None])
            ),
            snippet=_snippet(action.description, query) or _snippet(action.notes, query),
        )

    for commitment in (
        db.query(Commitment)
        .filter(or_(ilike(Commitment.title), ilike(Commitment.description), ilike(Commitment.origin_detail)))
        .order_by(Commitment.status.in_(["delivered", "dropped"]), Commitment.due_date.is_(None), Commitment.due_date)
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "commitment",
            commitment.id,
            commitment.title,
            f"/register?open=commitment-{commitment.id}",
            meta=" · ".join(
                filter(None, [commitment.status.replace("_", " "),
                              commitment.owner.name if commitment.owner else None,
                              f"from {commitment.origin}"])
            ),
            snippet=_snippet(commitment.description, query),
        )

    for topic in (
        db.query(Topic)
        .filter(or_(ilike(Topic.title), ilike(Topic.description)))
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "topic",
            topic.id,
            topic.title,
            f"/topics?open={topic.id}",
            meta=f"{topic.intent} · {topic.status}",
            snippet=_snippet(topic.description, query),
        )

    for decision in (
        db.query(Decision)
        .filter(or_(ilike(Decision.title), ilike(Decision.detail)))
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "decision",
            decision.id,
            decision.title,
            f"/meetings/{decision.meeting_id}" if decision.meeting_id else "/meetings",
            meta=" · ".join(
                filter(None, [decision.status, f"decided {decision.decided_on.isoformat()}" if decision.decided_on else None])
            ),
            snippet=_snippet(decision.detail, query),
        )

    for key_date in (
        db.query(KeyDate)
        .filter(or_(ilike(KeyDate.title), ilike(KeyDate.notes)))
        .order_by(KeyDate.date)
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "key_date",
            key_date.id,
            key_date.title,
            "/planner",
            meta=f"{key_date.date.isoformat()} · {key_date.kind.replace('_', ' ')}" + (" · hard" if key_date.hard else ""),
            snippet=_snippet(key_date.notes, query),
        )

    for workstream in (
        db.query(Workstream)
        .filter(or_(ilike(Workstream.name), ilike(Workstream.description)))
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "workstream",
            workstream.id,
            workstream.name,
            f"/register?workstream={workstream.id}",
            meta=f"{workstream.category} · {workstream.status}",
        )

    for forum in (
        db.query(Forum)
        .filter(or_(ilike(Forum.name), ilike(Forum.audience)))
        .limit(PER_TYPE_LIMIT)
    ):
        add("forum", forum.id, forum.name, "/meetings", meta=forum.cadence)

    for meeting in (
        db.query(Meeting).filter(ilike(Meeting.notes)).limit(PER_TYPE_LIMIT)
    ):
        add(
            "meeting",
            meeting.id,
            f"{meeting.forum.name} — {meeting.scheduled_at:%d %b %Y}",
            f"/meetings/{meeting.id}",
            meta=meeting.status.replace("_", " "),
            snippet=_snippet(meeting.notes, query),
        )

    for chase in (
        db.query(Chase).filter(ilike(Chase.note)).order_by(Chase.chased_on.desc()).limit(PER_TYPE_LIMIT)
    ):
        if chase.action_id and chase.action:
            title, url = chase.action.title, f"/register?open=action-{chase.action_id}"
        elif chase.commitment_id and chase.commitment:
            title, url = chase.commitment.title, f"/register?open=commitment-{chase.commitment_id}"
        else:
            continue
        add(
            "chase",
            chase.id,
            title,
            url,
            meta=f"chased {chase.chased_on.isoformat()} via {chase.method}",
            snippet=_snippet(chase.note, query),
        )

    for event in (
        db.query(DiaryEvent)
        .filter(
            DiaryEvent.status == "active",
            or_(ilike(DiaryEvent.subject), ilike(DiaryEvent.location), ilike(DiaryEvent.organizer)),
        )
        .order_by(DiaryEvent.start.desc())
        .limit(PER_TYPE_LIMIT)
    ):
        add(
            "diary_event",
            event.id,
            event.subject or "(no subject)",
            "/diary",
            meta=" · ".join(filter(None, [event.start_date, event.start_time, event.location])),
        )

    return {"query": query, "count": len(results), "results": results}
