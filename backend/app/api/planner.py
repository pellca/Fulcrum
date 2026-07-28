from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Commitment, KeyDate, Meeting, Workstream
from ..schemas import KeyDateIn, KeyDateOut, KeyDatePatch
from ..services.timeline import risk_chains

router = APIRouter(tags=["planner"])


@router.get("/key-dates", response_model=list[KeyDateOut])
def list_key_dates(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(KeyDate)
    if from_date:
        query = query.filter(KeyDate.date >= from_date)
    if to_date:
        query = query.filter(KeyDate.date <= to_date)
    return query.order_by(KeyDate.date).all()


@router.post("/key-dates", response_model=KeyDateOut, status_code=201)
def create_key_date(body: KeyDateIn, db: Session = Depends(get_db)):
    key_date = KeyDate(**body.model_dump())
    db.add(key_date)
    db.commit()
    return key_date


@router.patch("/key-dates/{item_id}", response_model=KeyDateOut)
def update_key_date(item_id: int, body: KeyDatePatch, db: Session = Depends(get_db)):
    key_date = db.get(KeyDate, item_id)
    if not key_date:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(key_date, key, value)
    db.commit()
    return key_date


@router.delete("/key-dates/{item_id}", status_code=204)
def delete_key_date(item_id: int, db: Session = Depends(get_db)):
    key_date = db.get(KeyDate, item_id)
    if key_date:
        db.delete(key_date)
        db.commit()


@router.get("/planner/timeline")
def timeline(weeks: int = 8, db: Session = Depends(get_db)):
    """Lane-per-workstream data for the forward planner."""
    today = date.today()
    horizon = today + timedelta(weeks=weeks)
    lanes = []
    workstreams = (
        db.query(Workstream).filter(Workstream.status == "active").order_by(Workstream.name).all()
    )
    unassigned = {"workstream": None, "commitments": [], "key_dates": []}
    lane_by_ws: dict[Optional[int], dict] = {None: unassigned}
    for ws in workstreams:
        lane = {
            "workstream": {"id": ws.id, "name": ws.name, "colour": ws.colour, "category": ws.category},
            "commitments": [],
            "key_dates": [],
        }
        lanes.append(lane)
        lane_by_ws[ws.id] = lane

    commitments = (
        db.query(Commitment)
        .filter(
            Commitment.status.notin_(["dropped"]),
            Commitment.due_date.isnot(None),
            Commitment.due_date <= horizon,
        )
        .all()
    )
    for commitment in commitments:
        lane = lane_by_ws.get(commitment.workstream_id, unassigned)
        lane["commitments"].append(
            {
                "id": commitment.id,
                "title": commitment.title,
                "due_date": commitment.due_date.isoformat(),
                "status": commitment.status,
                "priority": commitment.priority,
                "owner": commitment.owner.name if commitment.owner else None,
            }
        )

    key_dates = (
        db.query(KeyDate).filter(KeyDate.date >= today - timedelta(days=7), KeyDate.date <= horizon).all()
    )
    for kd in key_dates:
        lane = lane_by_ws.get(kd.workstream_id, unassigned)
        lane["key_dates"].append(
            {"id": kd.id, "title": kd.title, "date": kd.date.isoformat(), "kind": kd.kind, "hard": kd.hard}
        )

    meetings = (
        db.query(Meeting)
        .filter(Meeting.scheduled_at >= today, Meeting.scheduled_at <= horizon, Meeting.status != "cancelled")
        .order_by(Meeting.scheduled_at)
        .all()
    )
    meeting_rows = [
        {
            "id": m.id,
            "forum": m.forum.name,
            "colour": m.forum.colour,
            "scheduled_at": m.scheduled_at.isoformat(),
            "status": m.status,
        }
        for m in meetings
    ]

    if unassigned["commitments"] or unassigned["key_dates"]:
        lanes.append(unassigned)
    return {"from": today.isoformat(), "to": horizon.isoformat(), "lanes": lanes, "meetings": meeting_rows}


@router.get("/planner/risks")
def planner_risks(db: Session = Depends(get_db)):
    return risk_chains(db)
