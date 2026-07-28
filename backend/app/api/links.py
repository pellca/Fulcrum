from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Link
from ..schemas import LinkIn, LinkResolvedOut
from ..services.timeline import resolve_title

router = APIRouter(prefix="/links", tags=["links"])


def _resolve(db: Session, link: Link) -> Link:
    link.from_title = resolve_title(db, link.from_type, link.from_id)
    link.to_title = resolve_title(db, link.to_type, link.to_id)
    return link


@router.get("/for/{entity_type}/{entity_id}", response_model=list[LinkResolvedOut])
def links_for(entity_type: str, entity_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Link)
        .filter(
            ((Link.from_type == entity_type) & (Link.from_id == entity_id))
            | ((Link.to_type == entity_type) & (Link.to_id == entity_id))
        )
        .all()
    )
    return [_resolve(db, row) for row in rows]


@router.post("", response_model=LinkResolvedOut, status_code=201)
def create_link(body: LinkIn, db: Session = Depends(get_db)):
    link = Link(**body.model_dump())
    db.add(link)
    db.commit()
    return _resolve(db, link)


@router.delete("/{link_id}", status_code=204)
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.get(Link, link_id)
    if link:
        db.delete(link)
        db.commit()
