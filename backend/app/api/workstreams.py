from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Workstream
from ..schemas import WorkstreamIn, WorkstreamOut, WorkstreamPatch, WorkstreamReorder
from ..services.bulk import delete_entities, resolve_people

router = APIRouter(prefix="/workstreams", tags=["workstreams"])


def _ordered(query):
    """The one ordering every workstream list uses. `sort_order` is 0 until the
    user drags or types an order, so untouched data keeps the category/name
    ordering that predates the column."""
    return query.order_by(Workstream.sort_order, Workstream.category, Workstream.name)


@router.get("", response_model=list[WorkstreamOut])
def list_workstreams(include_closed: bool = False, db: Session = Depends(get_db)):
    query = db.query(Workstream).options(selectinload(Workstream.owners))
    if not include_closed:
        query = query.filter(Workstream.status != "closed")
    return _ordered(query).all()


@router.post("", response_model=WorkstreamOut, status_code=201)
def create_workstream(body: WorkstreamIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    owners = resolve_people(db, data.pop("owner_ids"))
    if data.get("sort_order") is None:
        # append rather than tie for first place — a new workstream landing at the
        # top of everyone's rolling agenda is never what was meant
        data["sort_order"] = (db.query(func.max(Workstream.sort_order)).scalar() or 0) + 1
    workstream = Workstream(**data)
    workstream.owners = owners
    db.add(workstream)
    db.commit()
    return workstream


@router.post("/reorder", response_model=list[WorkstreamOut])
def reorder_workstreams(body: WorkstreamReorder, db: Session = Depends(get_db)):
    """Renumber `sort_order` to 1..N in the order given. Ids not in the body keep
    their current number, so reordering a filtered list (the default view hides
    closed workstreams) does not disturb what is off-screen."""
    order = {ws_id: index + 1 for index, ws_id in enumerate(body.ids)}
    for workstream in db.query(Workstream).filter(Workstream.id.in_(order)).all():
        workstream.sort_order = order[workstream.id]
    db.commit()
    return _ordered(db.query(Workstream).options(selectinload(Workstream.owners))).all()


@router.patch("/{ws_id}", response_model=WorkstreamOut)
def update_workstream(ws_id: int, body: WorkstreamPatch, db: Session = Depends(get_db)):
    workstream = db.get(Workstream, ws_id)
    if not workstream:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "owner_ids":
            workstream.owners = resolve_people(db, value or [])
        else:
            setattr(workstream, key, value)
    db.commit()
    return workstream


@router.delete("/{ws_id}", status_code=204)
def delete_workstream(ws_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "workstream", [ws_id])
