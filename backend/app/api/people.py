from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Action, Commitment, Decision, Person, PersonAlias, PersonNote, Topic
from ..schemas import (
    AliasIn,
    MarkNotesDiscussedIn,
    PersonIn,
    PersonNoteIn,
    PersonNoteOut,
    PersonNotePatch,
    PersonOut,
    PersonPatch,
)
from ..services.bulk import check_references, delete_entities
from ..services.chase import latest_chase_map

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


@router.get("/{person_id}/references")
def person_references(person_id: int, db: Session = Depends(get_db)):
    """What deleting this person would leave unowned."""
    if not db.get(Person, person_id):
        raise HTTPException(404)
    return check_references(db, "person", [person_id])


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "person", [person_id])


@router.get("/{person_id}/pack")
def one_to_one_pack(person_id: int, db: Session = Depends(get_db)):
    """Everything you need in hand before a 1:1 with this person."""
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    today = date.today()
    soon = today + timedelta(days=14)
    latest = latest_chase_map(db)

    def item_row(item, kind: str) -> dict:
        chase = latest.get((kind, item.id))
        return {
            "id": item.id,
            "type": kind,
            "title": item.title,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status,
            "priority": item.priority,
            "workstream": item.workstream.name if item.workstream else None,
            "origin": getattr(item, "origin", None),
            "last_chased_on": chase.chased_on.isoformat() if chase else None,
            "next_chase_on": chase.next_chase_on.isoformat() if chase and chase.next_chase_on else None,
        }

    open_actions = (
        db.query(Action)
        .filter(Action.owner_id == person_id, Action.status.notin_(["done", "cancelled"]))
        .order_by(Action.due_date.is_(None), Action.due_date)
        .all()
    )
    open_commitments = (
        db.query(Commitment)
        .filter(Commitment.owner_id == person_id, Commitment.status.notin_(["delivered", "dropped"]))
        .order_by(Commitment.due_date.is_(None), Commitment.due_date)
        .all()
    )
    items = [item_row(a, "action") for a in open_actions] + [
        item_row(c, "commitment") for c in open_commitments
    ]

    overdue = [i for i in items if i["due_date"] and i["due_date"] < today.isoformat()]
    due_soon = [
        i for i in items if i["due_date"] and today.isoformat() <= i["due_date"] <= soon.isoformat()
    ]
    later = [i for i in items if i not in overdue and i not in due_soon]
    waiting_on = sorted(
        (i for i in items if i["next_chase_on"] and i["next_chase_on"] <= today.isoformat()),
        key=lambda i: i["next_chase_on"],
    )

    decisions = (
        db.query(Decision)
        .filter(
            Decision.owner_id == person_id,
            (Decision.status.in_(["pending", "revisit"]))
            | ((Decision.review_on.isnot(None)) & (Decision.review_on <= soon)),
        )
        .order_by(Decision.review_on.is_(None), Decision.review_on)
        .all()
    )
    topics = (
        db.query(Topic)
        .filter(Topic.sponsors.any(Person.id == person_id), Topic.status.in_(["proposed", "parked"]))
        .order_by(Topic.target_by.is_(None), Topic.target_by)
        .all()
    )
    undiscussed_notes = (
        db.query(PersonNote)
        .filter(PersonNote.person_id == person_id, PersonNote.discussed_on.is_(None))
        .order_by(PersonNote.noted_on.desc(), PersonNote.id.desc())
        .all()
    )

    return {
        "person": {
            "id": person.id,
            "name": person.name,
            "role": person.role,
            "team": person.team,
        },
        "generated": today.isoformat(),
        "overdue": sorted(overdue, key=lambda i: i["due_date"]),
        "due_soon": sorted(due_soon, key=lambda i: i["due_date"]),
        "later": later,
        "waiting_on": waiting_on,
        "decisions": [
            {
                "id": d.id,
                "title": d.title,
                "status": d.status,
                "decided_on": d.decided_on.isoformat() if d.decided_on else None,
                "review_on": d.review_on.isoformat() if d.review_on else None,
            }
            for d in decisions
        ],
        "topics": [
            {
                "id": t.id,
                "title": t.title,
                "intent": t.intent,
                "readiness": t.readiness,
                "status": t.status,
                "target_by": t.target_by.isoformat() if t.target_by else None,
                "duration_minutes": t.duration_minutes,
            }
            for t in topics
        ],
        "notes": [
            {
                "id": n.id,
                "kind": n.kind,
                "note": n.note,
                "noted_on": n.noted_on.isoformat() if n.noted_on else None,
                "source": n.source,
            }
            for n in undiscussed_notes
        ],
    }


@router.post("/{person_id}/aliases", response_model=PersonOut)
def add_alias(person_id: int, body: AliasIn, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404)
    alias = (body.alias or "").strip()
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


@router.get("/{person_id}/notes", response_model=list[PersonNoteOut])
def list_person_notes(
    person_id: int,
    kind: str | None = None,
    undiscussed: bool | None = None,
    db: Session = Depends(get_db),
):
    if not db.get(Person, person_id):
        raise HTTPException(404)
    query = db.query(PersonNote).filter(PersonNote.person_id == person_id)
    if kind is not None:
        query = query.filter(PersonNote.kind == kind)
    if undiscussed:
        query = query.filter(PersonNote.discussed_on.is_(None))
    return query.order_by(PersonNote.noted_on.desc(), PersonNote.id.desc()).all()


@router.post("/{person_id}/notes", response_model=PersonNoteOut, status_code=201)
def add_person_note(person_id: int, body: PersonNoteIn, db: Session = Depends(get_db)):
    if not db.get(Person, person_id):
        raise HTTPException(404)
    data = body.model_dump()
    if data["noted_on"] is None:
        data["noted_on"] = date.today()
    note = PersonNote(person_id=person_id, **data)
    db.add(note)
    db.commit()
    return note


@router.post("/{person_id}/notes/mark-discussed")
def mark_notes_discussed(
    person_id: int, body: MarkNotesDiscussedIn | None = None, db: Session = Depends(get_db)
):
    if not db.get(Person, person_id):
        raise HTTPException(404)
    ids = body.ids if body else None
    query = db.query(PersonNote).filter(
        PersonNote.person_id == person_id, PersonNote.discussed_on.is_(None)
    )
    if ids is not None:
        query = query.filter(PersonNote.id.in_(ids))
    notes = query.all()
    today = date.today()
    for note in notes:
        note.discussed_on = today
    db.commit()
    return {"marked": len(notes)}


@router.patch("/notes/{note_id}", response_model=PersonNoteOut)
def update_person_note(note_id: int, body: PersonNotePatch, db: Session = Depends(get_db)):
    note = db.get(PersonNote, note_id)
    if not note:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    db.commit()
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_person_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(PersonNote, note_id)
    if note:
        db.delete(note)
        db.commit()
