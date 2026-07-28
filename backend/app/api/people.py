from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Person, PersonAlias
from ..schemas import PersonIn, PersonOut, PersonPatch

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[PersonOut])
def list_people(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(Person)
    if not include_inactive:
        query = query.filter(Person.active.is_(True))
    return query.order_by(Person.name).all()


@router.post("", response_model=PersonOut, status_code=201)
def create_person(body: PersonIn, db: Session = Depends(get_db)):
    person = Person(**body.model_dump())
    db.add(person)
    db.commit()
    return person


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(person_id: int, body: PersonPatch, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(person, key, value)
    db.commit()
    return person


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if person:
        db.delete(person)
        db.commit()


@router.post("/{person_id}/aliases", response_model=PersonOut)
def add_alias(person_id: int, body: dict, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    alias = (body.get("alias") or "").strip()
    if not alias:
        raise HTTPException(422, "alias required")
    existing = db.query(PersonAlias).filter(PersonAlias.alias == alias).first()
    if existing:
        raise HTTPException(409, f"Alias already mapped to {existing.person.name}")
    db.add(PersonAlias(alias=alias, person_id=person_id))
    db.commit()
    db.refresh(person)
    return person


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, db: Session = Depends(get_db)):
    alias = db.get(PersonAlias, alias_id)
    if alias:
        db.delete(alias)
        db.commit()
