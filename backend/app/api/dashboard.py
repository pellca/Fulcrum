from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Action, Commitment, KeyDate, Meeting, Topic
from ..services.chase import chase_queue

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
            "sponsor": t.sponsor.name if t.sponsor else None,
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

    meetings = []
    for meeting in (
        db.query(Meeting)
        .filter(
            Meeting.scheduled_at >= datetime.combine(today, datetime.min.time()),
            Meeting.scheduled_at <= datetime.combine(today + timedelta(days=14), datetime.max.time()),
            Meeting.status != "cancelled",
        )
        .order_by(Meeting.scheduled_at)
    ):
        allocated = sum(item.allocated_minutes for item in meeting.agenda_items)
        meetings.append(
            {
                "id": meeting.id,
                "forum": meeting.forum.name,
                "colour": meeting.forum.colour,
                "scheduled_at": meeting.scheduled_at.isoformat(),
                "status": meeting.status,
                "needs_review": meeting.needs_review,
                "agenda_count": len(meeting.agenda_items),
                "allocated_minutes": allocated,
                "capacity_minutes": meeting.forum.capacity_minutes,
            }
        )

    return {
        "today": today.isoformat(),
        "overdue_actions": overdue_actions,
        "due_soon_actions": due_soon_actions,
        "overdue_commitments": overdue_commitments,
        "due_soon_commitments": due_soon_commitments,
        "chase_queue": chase_queue(db, today),
        "decision_ready": decision_ready,
        "key_dates": key_dates,
        "meetings": meetings,
    }
