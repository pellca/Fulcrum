from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Workstream
from ..schemas import WorkstreamIn, WorkstreamOut, WorkstreamPatch

router = APIRouter(prefix="/workstreams", tags=["workstreams"])


@router.get("", response_model=list[WorkstreamOut])
def list_workstreams(include_closed: bool = False, db: Session = Depends(get_db)):
    query = db.query(Workstream)
    if not include_closed:
        query = query.filter(Workstream.status != "closed")
    return query.order_by(Workstream.name).all()


@router.post("", response_model=WorkstreamOut, status_code=201)
def create_workstream(body: WorkstreamIn, db: Session = Depends(get_db)):
    workstream = Workstream(**body.model_dump())
    db.add(workstream)
    db.commit()
    return workstream


@router.patch("/{ws_id}", response_model=WorkstreamOut)
def update_workstream(ws_id: int, body: WorkstreamPatch, db: Session = Depends(get_db)):
    workstream = db.get(Workstream, ws_id)
    if not workstream:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(workstream, key, value)
    db.commit()
    return workstream


@router.delete("/{ws_id}", status_code=204)
def delete_workstream(ws_id: int, db: Session = Depends(get_db)):
    workstream = db.get(Workstream, ws_id)
    if workstream:
        db.delete(workstream)
        db.commit()
