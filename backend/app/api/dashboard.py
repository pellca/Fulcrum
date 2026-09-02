from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Action, Commitment, Decision, DiaryEvent, KeyDate, Meeting, Person, Topic
from ..services.chase import chase_queue
from ..services.discussion import discussion_list

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _action_row(action: Action) -> dict:
    return {
        "id": action.id,
        "title": action.title,
        "owner": action.owner.name if action.owner else None,
        "due_date": action.due_date.isoformat() if action.due_date else None,
        "status": action.status,
        "priority": action.priority,
        "workstream": action.workstream.name if action.workstream else None,
    }


def _commitment_row(commitment: Commitment) -> dict:
    return {
        "id": commitment.id,
        "title": commitment.title,
        "owner": commitment.owner.name if commitment.owner else None,
        "due_date": commitment.due_date.isoformat() if commitment.due_date else None,
        "status": commitment.status,
        "priority": commitment.priority,
        "origin": commitment.origin,
        "workstream": commitment.workstream.name if commitment.workstream else None,
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    today = date.today()
    soon = today + timedelta(days=7)

    open_actions = db.query(Action).filter(Action.status.notin_(["done", "cancelled"]))
    open_commitments = db.query(Commitment).filter(
        Commitment.status.notin_(["delivered", "dropped"])
    )

    overdue_actions = [
        _action_row(a)
        for a in open_actions.filter(Action.due_date < today).order_by(Action.due_date)
    ]
    due_soon_actions = [
        _action_row(a)
        for a in open_actions.filter(Action.due_date >= today, Action.due_date <= soon).order_by(
            Action.due_date
        )
    ]
    overdue_commitments = [
        _commitment_row(c)
        for c in open_commitments.filter(Commitment.due_date < today).order_by(Commitment.due_date)
    ]
    due_soon_commitments = [
        _commitment_row(c)
        for c in open_commitments.filter(
            Commitment.due_date >= today, Commitment.due_date <= soon
        ).order_by(Commitment.due_date)
    ]

    decision_ready = [
        {
            "id": t.id,
            "title": t.title,
            "sponsor": ", ".join(p.name for p in t.sponsors) or None,
            "target_by": t.target_by.isoformat() if t.target_by else None,
            "duration_minutes": t.duration_minutes,
        }
        for t in db.query(Topic)
        .filter(Topic.intent == "decide", Topic.readiness == "ready", Topic.status == "proposed")
        .order_by(Topic.target_by.is_(None), Topic.target_by)
    ]

    key_dates = [
        {
            "id": kd.id,
            "title": kd.title,
            "date": kd.date.isoformat(),
            "kind": kd.kind,
            "hard": kd.hard,
            "days_away": (kd.date - today).days,
            "workstream": kd.workstream.name if kd.workstream else None,
        }
        for kd in db.query(KeyDate)
        .filter(KeyDate.date >= today, KeyDate.date <= today + timedelta(days=30))
        .order_by(KeyDate.date)
    ]

    # Today's diary, not "meetings happening to have a Fulcrum agenda" — most
    # of what's actually in the diary was never created as a Meeting, so that
    # slice was a poor stand-in for "what does today look like". start_date/
    # start_time are stored as strings (YYYY-MM-DD/HH:MM); compare as strings,
    # don't parse — start_date is already indexed.
    #
    # Anything *spanning* today counts, not just what starts today: a three-day
    # offsite or a week of leave has to stay on the brief for its whole run,
    # and matching on start_date alone dropped it after day one. A null
    # end_date means a single-day event, hence the coalesce.
    today_str = today.isoformat()
    diary_events = (
        db.query(DiaryEvent)
        .filter(
            DiaryEvent.start_date <= today_str,
            func.coalesce(DiaryEvent.end_date, DiaryEvent.start_date) >= today_str,
            DiaryEvent.status == "active",
        )
        .order_by(DiaryEvent.is_all_day.desc(), DiaryEvent.start_time)
        .all()
    )

    def _span(event: DiaryEvent) -> tuple[int, int]:
        """(which day of the event today is, how many days it runs) — 1-based,
        so a single-day entry is (1, 1) and the UI knows to say nothing."""
        try:
            start = date.fromisoformat(event.start_date)
            end = date.fromisoformat(event.end_date or event.start_date)
        except (TypeError, ValueError):
            return 1, 1
        return (today - start).days + 1, (end - start).days + 1

    # Batch-resolve the Fulcrum side in one query — never one per event.
    event_ids = [e.id for e in diary_events]
    linked_meetings: dict[str, Meeting] = {}
    if event_ids:
        for meeting in (
            db.query(Meeting)
            .filter(Meeting.diary_event_id.in_(event_ids))
            .options(selectinload(Meeting.agenda_items), selectinload(Meeting.forum))
            .all()
        ):
            linked_meetings[meeting.diary_event_id] = meeting

    def _meeting_row(meeting: Meeting | None) -> dict | None:
        if meeting is None:
            return None
        allocated = sum(item.allocated_minutes for item in meeting.agenda_items)
        return {
            "id": meeting.id,
            "forum": meeting.forum.name,
            "colour": meeting.forum.colour,
            "status": meeting.status,
            "needs_review": meeting.needs_review,
            "agenda_count": len(meeting.agenda_items),
            "allocated_minutes": allocated,
            "capacity_minutes": meeting.forum.capacity_minutes,
        }

    diary = [
        {
            "id": event.id,
            "subject": event.subject,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "is_all_day": event.is_all_day,
            "location": event.location,
            "organizer": event.organizer,
            "span_day": _span(event)[0],
            "span_days": _span(event)[1],
            "meeting": _meeting_row(linked_meetings.get(event.id)),
        }
        for event in diary_events
    ]

    # One indexed EXISTS, so the dashboard can tell "nothing on today" from
    # "no diary has ever been imported" without the client making a second
    # round trip to /admin/stats — which counts every table in the database.
    diary_imported = db.query(DiaryEvent.id).first() is not None

    decisions_for_review = [
        {
            "id": d.id,
            "title": d.title,
            "status": d.status,
            "owner": d.owner.name if d.owner else None,
            "decided_on": d.decided_on.isoformat() if d.decided_on else None,
            "review_on": d.review_on.isoformat() if d.review_on else None,
            "days_overdue": (today - d.review_on).days if d.review_on else 0,
        }
        for d in db.query(Decision)
        .filter(Decision.review_on.isnot(None), Decision.review_on <= today)
        .order_by(Decision.review_on)
    ]

    pinned = db.query(Person).filter(Person.pin_discussion.is_(True)).first()
    discussion = (
        {"person": {"id": pinned.id, "name": pinned.name}, "points": discussion_list(db, pinned.id)}
        if pinned
        else None
    )

    return {
        "today": today.isoformat(),
        "discussion": discussion,
        "decisions_for_review": decisions_for_review,
        "overdue_actions": overdue_actions,
        "due_soon_actions": due_soon_actions,
        "overdue_commitments": overdue_commitments,
        "due_soon_commitments": due_soon_commitments,
        "chase_queue": chase_queue(db, today),
        "decision_ready": decision_ready,
        "key_dates": key_dates,
        "diary": diary,
        "diary_imported": diary_imported,
    }
