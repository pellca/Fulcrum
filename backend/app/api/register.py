from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Action, Chase, Commitment
from ..schemas import (
    ActionIn,
    ActionOut,
    ActionPatch,
    ChaseIn,
    ChaseOut,
    CommitmentIn,
    CommitmentOut,
    CommitmentPatch,
    QuickAddIn,
)
from ..services.chase import latest_chase_map, next_chase_for
from ..services.quickadd import parse_quickadd

router = APIRouter(tags=["register"])


def _enrich_commitments(db: Session, rows: list[Commitment]) -> list[Commitment]:
    latest = latest_chase_map(db)
    for row in rows:
        row.action_count = len(row.actions)
        chase = latest.get(("commitment", row.id))
        row.next_chase_on = chase.next_chase_on if chase else None
    return rows


def _enrich_actions(db: Session, rows: list[Action]) -> list[Action]:
    latest = latest_chase_map(db)
    for row in rows:
        chase = latest.get(("action", row.id))
        row.next_chase_on = chase.next_chase_on if chase else None
    return rows


@router.get("/commitments", response_model=list[CommitmentOut])
def list_commitments(
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    workstream_id: Optional[int] = None,
    origin: Optional[str] = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Commitment)
    if status:
        query = query.filter(Commitment.status == status)
    if open_only:
        query = query.filter(Commitment.status.notin_(["delivered", "dropped"]))
    if owner_id:
        query = query.filter(Commitment.owner_id == owner_id)
    if workstream_id:
        query = query.filter(Commitment.workstream_id == workstream_id)
    if origin:
        query = query.filter(Commitment.origin == origin)
    rows = query.order_by(Commitment.due_date.is_(None), Commitment.due_date).all()
    return _enrich_commitments(db, rows)


@router.post("/commitments", response_model=CommitmentOut, status_code=201)
def create_commitment(body: CommitmentIn, db: Session = Depends(get_db)):
    commitment = Commitment(**body.model_dump())
    db.add(commitment)
    db.commit()
    return _enrich_commitments(db, [commitment])[0]


@router.get("/commitments/{item_id}", response_model=CommitmentOut)
def get_commitment(item_id: int, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, item_id)
    if not commitment:
        raise HTTPException(404)
    return _enrich_commitments(db, [commitment])[0]


@router.patch("/commitments/{item_id}", response_model=CommitmentOut)
def update_commitment(item_id: int, body: CommitmentPatch, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, item_id)
    if not commitment:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(commitment, key, value)
    db.commit()
    return _enrich_commitments(db, [commitment])[0]


@router.delete("/commitments/{item_id}", status_code=204)
def delete_commitment(item_id: int, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, item_id)
    if commitment:
        db.delete(commitment)
        db.commit()


@router.get("/actions", response_model=list[ActionOut])
def list_actions(
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    workstream_id: Optional[int] = None,
    commitment_id: Optional[int] = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Action)
    if status:
        query = query.filter(Action.status == status)
    if open_only:
        query = query.filter(Action.status.notin_(["done", "cancelled"]))
    if owner_id:
        query = query.filter(Action.owner_id == owner_id)
    if workstream_id:
        query = query.filter(Action.workstream_id == workstream_id)
    if commitment_id:
        query = query.filter(Action.commitment_id == commitment_id)
    rows = query.order_by(Action.due_date.is_(None), Action.due_date).all()
    return _enrich_actions(db, rows)


@router.post("/actions", response_model=ActionOut, status_code=201)
def create_action(body: ActionIn, db: Session = Depends(get_db)):
    action = Action(**body.model_dump())
    db.add(action)
    db.commit()
    return _enrich_actions(db, [action])[0]


@router.get("/actions/{item_id}", response_model=ActionOut)
def get_action(item_id: int, db: Session = Depends(get_db)):
    action = db.get(Action, item_id)
    if not action:
        raise HTTPException(404)
    return _enrich_actions(db, [action])[0]


@router.patch("/actions/{item_id}", response_model=ActionOut)
def update_action(item_id: int, body: ActionPatch, db: Session = Depends(get_db)):
    action = db.get(Action, item_id)
    if not action:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(action, key, value)
    db.commit()
    return _enrich_actions(db, [action])[0]


@router.delete("/actions/{item_id}", status_code=204)
def delete_action(item_id: int, db: Session = Depends(get_db)):
    action = db.get(Action, item_id)
    if action:
        db.delete(action)
        db.commit()


@router.get("/chases", response_model=list[ChaseOut])
def list_chases(
    action_id: Optional[int] = None,
    commitment_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Chase)
    if action_id:
        query = query.filter(Chase.action_id == action_id)
    if commitment_id:
        query = query.filter(Chase.commitment_id == commitment_id)
    return query.order_by(Chase.chased_on.desc(), Chase.id.desc()).all()


@router.post("/chases", response_model=ChaseOut, status_code=201)
def create_chase(body: ChaseIn, db: Session = Depends(get_db)):
    if not body.action_id and not body.commitment_id:
        raise HTTPException(422, "action_id or commitment_id required")
    chase = Chase(**body.model_dump())
    db.add(chase)
    db.commit()
    return chase


@router.post("/quickadd/preview")
def quickadd_preview(body: QuickAddIn, db: Session = Depends(get_db)):
    return parse_quickadd(db, body.text)


@router.post("/quickadd", status_code=201)
def quickadd(body: QuickAddIn, db: Session = Depends(get_db)):
    parsed = parse_quickadd(db, body.text)
    if not parsed["title"]:
        raise HTTPException(422, "No title after removing tokens")
    if body.type == "commitment":
        item = Commitment(
            title=parsed["title"],
            owner_id=parsed["owner_id"],
            workstream_id=parsed["workstream_id"],
            due_date=parsed["due_date"],
            priority=parsed["priority"],
            origin=parsed["origin"] or "principal",
        )
    elif body.type == "topic":
        from ..models import Topic

        item = Topic(
            title=parsed["title"],
            sponsor_id=parsed["owner_id"],
            workstream_id=parsed["workstream_id"],
            target_by=parsed["due_date"],
        )
    else:
        item = Action(
            title=parsed["title"],
            owner_id=parsed["owner_id"],
            workstream_id=parsed["workstream_id"],
            due_date=parsed["due_date"],
            priority=parsed["priority"],
        )
    db.add(item)
    db.commit()
    return {"type": body.type, "id": item.id, "title": item.title, "warnings": parsed["warnings"]}
