from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DiscussionPoint, Link, Person
from ..schemas import DiscussionPointIn, DiscussionPointOut, DiscussionPointPatch
from ..services.bulk import delete_entities
from ..services.discussion import discussion_list

router = APIRouter(prefix="/discussion-points", tags=["discussion"])


def _row(db: Session, point: DiscussionPoint) -> dict:
    """Refetch through the shared builder so a write response has its links
    resolved exactly the way every read does — no second code path to drift."""
    return next(r for r in discussion_list(db, point.person_id, include_closed=True) if r["id"] == point.id)


@router.get("", response_model=list[DiscussionPointOut])
def list_discussion_points(
    person_id: Optional[int] = None, include_closed: bool = False, db: Session = Depends(get_db)
):
    if person_id is not None:
        if not db.get(Person, person_id):
            raise HTTPException(404)
        return discussion_list(db, person_id, include_closed)

    # No person given: the generic link-target picker (LINKABLE in
    # panels.tsx) browses across everyone's list, so it has no person to
    # scope by. Link chips aren't needed there — only id/title — so skip the
    # per-point link resolution discussion_list does.
    query = db.query(DiscussionPoint)
    if not include_closed:
        query = query.filter(DiscussionPoint.status == "open")
    return [
        {
            "id": p.id,
            "person_id": p.person_id,
            "title": p.title,
            "detail": p.detail,
            "priority": p.priority,
            "status": p.status,
            "raised_on": p.raised_on,
            "last_discussed_on": p.last_discussed_on,
            "times_discussed": p.times_discussed,
            "closed_on": p.closed_on,
            "outcome": p.outcome,
            "links": [],
        }
        for p in query.order_by(DiscussionPoint.title).all()
    ]


@router.post("", response_model=DiscussionPointOut, status_code=201)
def create_discussion_point(body: DiscussionPointIn, db: Session = Depends(get_db)):
    if not db.get(Person, body.person_id):
        raise HTTPException(404, "Unknown person")
    data = body.model_dump(exclude={"link_to"})
    point = DiscussionPoint(raised_on=date.today(), **data)
    db.add(point)
    db.flush()
    if body.link_to:
        db.add(
            Link(
                from_type="discussion_point",
                from_id=point.id,
                to_type=body.link_to.type,
                to_id=body.link_to.id,
            )
        )
    db.commit()
    return _row(db, point)


@router.patch("/{point_id}", response_model=DiscussionPointOut)
def update_discussion_point(point_id: int, body: DiscussionPointPatch, db: Session = Depends(get_db)):
    point = db.get(DiscussionPoint, point_id)
    if not point:
        raise HTTPException(404)
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(point, key, value)
    if "status" in updates:
        # server-stamped, not client-supplied — closing and reopening should
        # not require the caller to also manage this date
        point.closed_on = date.today() if point.status == "closed" else None
    db.commit()
    return _row(db, point)


@router.post("/{point_id}/discussed", response_model=DiscussionPointOut)
def mark_discussed(point_id: int, db: Session = Depends(get_db)):
    point = db.get(DiscussionPoint, point_id)
    if not point:
        raise HTTPException(404)
    today = date.today()
    if point.last_discussed_on != today:
        point.last_discussed_on = today
        point.times_discussed += 1
        db.commit()
    return _row(db, point)


@router.delete("/{point_id}", status_code=204)
def delete_discussion_point(point_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "discussion_point", [point_id])
