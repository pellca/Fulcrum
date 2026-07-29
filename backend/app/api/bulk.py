from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.bulk import check_references, delete_entities

router = APIRouter(prefix="/bulk", tags=["bulk"])


class BulkIn(BaseModel):
    type: str
    ids: list  # ints for most types, strings for diary events


@router.post("/check")
def bulk_check(body: BulkIn, db: Session = Depends(get_db)):
    """Preflight a delete: what exists, and what it would orphan or remove."""
    try:
        return check_references(db, body.type, body.ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/delete")
def bulk_delete(body: BulkIn, db: Session = Depends(get_db)):
    try:
        return delete_entities(db, body.type, body.ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
