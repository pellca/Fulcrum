from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased, joinedload

from ..db import get_db
from ..models import Action, Chase, Commitment, Link, Person, PersonNote, Topic
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
from ..services.bulk import delete_entities, resolve_people
from ..services.chase import latest_chase_map, next_chase_for
from ..services.quickadd import parse_quickadd
from ..services.register_export import build_export
from .search import _like

router = APIRouter(tags=["register"])

PICKER_MAX_LIMIT = 50
PICKER_DEFAULT_LIMIT = 20


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


@router.get("/register/picker")
def picker(q: str = "", limit: int = PICKER_DEFAULT_LIMIT, db: Session = Depends(get_db)):
    query = q.strip()
    limit = max(1, min(PICKER_MAX_LIMIT, limit))
    if len(query) < 2:
        return {"items": []}

    like = _like(query)

    def item(kind: str, row) -> dict:
        owner = row.owner
        return {
            "type": kind,
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "due_date": row.due_date,
            "owner": {"id": owner.id, "name": owner.name} if owner else None,
        }

    action_owner = aliased(Person)
    actions = (
        db.query(Action)
        .options(joinedload(Action.owner))
        .outerjoin(action_owner, Action.owner_id == action_owner.id)
        .filter(Action.status.notin_(["done", "cancelled"]))
        .filter(
            or_(Action.title.ilike(like, escape="\\"), action_owner.name.ilike(like, escape="\\"))
        )
        .order_by(Action.title.asc())
        .limit(limit)
        .all()
    )
    commitment_owner = aliased(Person)
    commitments = (
        db.query(Commitment)
        .options(joinedload(Commitment.owner))
        .outerjoin(commitment_owner, Commitment.owner_id == commitment_owner.id)
        .filter(Commitment.status.notin_(["delivered", "dropped"]))
        .filter(
            or_(
                Commitment.title.ilike(like, escape="\\"),
                commitment_owner.name.ilike(like, escape="\\"),
            )
        )
        .order_by(Commitment.title.asc())
        .limit(limit)
        .all()
    )

    # actions typically far outnumber matching commitments, so a plain
    # actions-first truncation to `limit` can saturate the whole page with
    # actions and make a matching commitment unreachable -- reserve a slice
    # of the limit for commitments before truncating either side
    commitment_slots = min(len(commitments), max(1, limit // 4))
    action_slots = limit - min(commitment_slots, len(commitments))
    items = [item("action", row) for row in actions[:action_slots]] + [
        item("commitment", row) for row in commitments[:commitment_slots]
    ]
    return {"items": items}


@router.get("/register/export")
def export_register(
    format: str = "csv",
    chases: bool = False,
    links: bool = False,
    db: Session = Depends(get_db),
):
    if format not in ("csv", "xlsx"):
        raise HTTPException(422, "format must be 'csv' or 'xlsx'")
    content, media_type, extension = build_export(db, format=format, chases=chases, links=links)
    filename = f"fulcrum-register-{date.today().strftime('%Y%m%d')}.{extension}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    delete_entities(db, "commitment", [item_id])


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
    delete_entities(db, "action", [item_id])


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


# ---------- action <-> commitment conversion ----------

ACTION_TO_COMMITMENT_STATUS = {
    "todo": "open",
    "in_progress": "on_track",
    "blocked": "at_risk",
    "done": "delivered",
    "cancelled": "dropped",
}
COMMITMENT_TO_ACTION_STATUS = {v: k for k, v in ACTION_TO_COMMITMENT_STATUS.items()}


def _rewrite_links(db: Session, old_type: str, old_id: int, new_type: str, new_id: int) -> None:
    links = (
        db.query(Link)
        .filter(
            or_(
                (Link.from_type == old_type) & (Link.from_id == old_id),
                (Link.to_type == old_type) & (Link.to_id == old_id),
            )
        )
        .all()
    )
    for link in links:
        if link.from_type == old_type and link.from_id == old_id:
            link.from_type, link.from_id = new_type, new_id
        if link.to_type == old_type and link.to_id == old_id:
            link.to_type, link.to_id = new_type, new_id


class ConvertActionIn(BaseModel):
    origin: Optional[str] = "principal"  # who the new commitment is owed to


@router.post("/actions/{item_id}/convert", response_model=CommitmentOut)
def convert_action_to_commitment(
    item_id: int, body: ConvertActionIn, db: Session = Depends(get_db)
):
    action = db.get(Action, item_id)
    if not action:
        raise HTTPException(404)
    description = action.description or ""
    if action.notes:
        description = (description + "\n\n" if description else "") + f"[Notes] {action.notes}"
    commitment = Commitment(
        title=action.title,
        description=description or None,
        owner_id=action.owner_id,
        workstream_id=action.workstream_id,
        due_date=action.due_date,
        priority=action.priority,
        origin=body.origin or "principal",
        status=ACTION_TO_COMMITMENT_STATUS.get(action.status, "open"),
        is_demo=action.is_demo,
        created_at=action.created_at,
    )
    db.add(commitment)
    db.flush()

    db.query(Chase).filter(Chase.action_id == item_id).update(
        {"action_id": None, "commitment_id": commitment.id}, synchronize_session=False
    )
    _rewrite_links(db, "action", item_id, "commitment", commitment.id)
    if action.commitment_id:
        db.add(
            Link(
                from_type="commitment",
                from_id=commitment.id,
                to_type="commitment",
                to_id=action.commitment_id,
                kind="relates",
                rationale="Was a delivery action of this commitment before conversion",
            )
        )
    db.delete(action)
    db.commit()
    return _enrich_commitments(db, [commitment])[0]


@router.post("/commitments/{item_id}/convert", response_model=ActionOut)
def convert_commitment_to_action(item_id: int, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, item_id)
    if not commitment:
        raise HTTPException(404)
    notes = f"Origin before conversion: {commitment.origin}" + (
        f" ({commitment.origin_detail})" if commitment.origin_detail else ""
    )
    action = Action(
        title=commitment.title,
        description=commitment.description,
        owner_id=commitment.owner_id,
        workstream_id=commitment.workstream_id,
        due_date=commitment.due_date,
        priority=commitment.priority,
        status=COMMITMENT_TO_ACTION_STATUS.get(commitment.status, "todo"),
        notes=notes,
        is_demo=commitment.is_demo,
        created_at=commitment.created_at,
    )
    db.add(action)
    db.flush()

    db.query(Chase).filter(Chase.commitment_id == item_id).update(
        {"commitment_id": None, "action_id": action.id}, synchronize_session=False
    )
    _rewrite_links(db, "commitment", item_id, "action", action.id)
    # former delivery actions and topics keep a visible tie instead of a dead FK
    for child in db.query(Action).filter(Action.commitment_id == item_id):
        child.commitment_id = None
        db.add(
            Link(
                from_type="action",
                from_id=action.id,
                to_type="action",
                to_id=child.id,
                kind="relates",
                rationale="Was a delivery action of this item before conversion",
            )
        )
    for topic in db.query(Topic).filter(Topic.commitment_id == item_id):
        topic.commitment_id = None
        db.add(
            Link(
                from_type="topic",
                from_id=topic.id,
                to_type="action",
                to_id=action.id,
                kind="relates",
                rationale="Was linked to this item before conversion",
            )
        )
    db.delete(commitment)
    db.commit()
    return _enrich_actions(db, [action])[0]


@router.post("/quickadd/preview")
def quickadd_preview(body: QuickAddIn, db: Session = Depends(get_db)):
    return parse_quickadd(db, body.text)


@router.post("/quickadd", status_code=201)
def quickadd(body: QuickAddIn, db: Session = Depends(get_db)):
    parsed = parse_quickadd(db, body.text)
    if not parsed["title"]:
        raise HTTPException(422, "No title after removing tokens")
    if body.type == "note":
        if parsed["owner_id"] is None:
            raise HTTPException(422, "A note needs a matching @person")
        item = PersonNote(
            person_id=parsed["owner_id"],
            note=parsed["title"],
            kind=parsed["kind"] or "general",
            noted_on=date.today(),
            source="manual",
        )
        db.add(item)
        db.commit()
        return {
            "type": body.type,
            "id": item.id,
            "title": item.note,
            "warnings": parsed["warnings"],
        }
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
            sponsors=resolve_people(db, [parsed["owner_id"]] if parsed["owner_id"] else []),
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
