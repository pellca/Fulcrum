import json
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import IMPORTS_DIR
from ..db import get_db
from ..models import DiaryEvent, Meeting, Person, PersonAlias
from ..schemas import DiaryEventOut
from ..services.diary_import import import_diary_file, unmatched_attendees

router = APIRouter(prefix="/diary", tags=["diary"])


@router.get("/events", response_model=list[DiaryEventOut])
def list_events(
    from_date: str | None = None,
    to_date: str | None = None,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(DiaryEvent)
    if not include_cancelled:
        query = query.filter(DiaryEvent.status == "active")
    if from_date:
        query = query.filter(DiaryEvent.start_date >= from_date)
    if to_date:
        query = query.filter(DiaryEvent.start_date <= to_date)
    return query.order_by(DiaryEvent.start).all()


class ImportPathIn(BaseModel):
    path: str


@router.post("/import")
def import_from_path(body: ImportPathIn, db: Session = Depends(get_db)):
    try:
        return import_diary_file(db, body.path)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {body.path}")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/import-upload")
async def import_from_upload(file: UploadFile, db: Session = Depends(get_db)):
    destination = IMPORTS_DIR / f"diary-{int(time.time())}.json"
    destination.write_bytes(await file.read())
    try:
        return import_diary_file(db, destination)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/unmatched-attendees")
def get_unmatched(db: Session = Depends(get_db)):
    return unmatched_attendees(db)


class MapAttendeeIn(BaseModel):
    alias: str
    person_id: int | None = None  # None -> create a new person with this name


@router.post("/map-attendee")
def map_attendee(body: MapAttendeeIn, db: Session = Depends(get_db)):
    alias = body.alias.strip()
    if not alias:
        raise HTTPException(422, "alias required")
    person_id = body.person_id
    if person_id is None:
        person = Person(name=alias)
        db.add(person)
        db.flush()
        person_id = person.id
    else:
        if not db.get(Person, person_id):
            raise HTTPException(404, "Unknown person")
        db.add(PersonAlias(alias=alias, person_id=person_id))
    db.commit()
    return {"alias": alias, "person_id": person_id}


class LinkMeetingIn(BaseModel):
    meeting_id: int
    diary_event_id: str | None  # None unlinks


@router.post("/link-meeting")
def link_meeting(body: LinkMeetingIn, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, body.meeting_id)
    if not meeting:
        raise HTTPException(404, "Unknown meeting")
    if body.diary_event_id and not db.get(DiaryEvent, body.diary_event_id):
        raise HTTPException(404, "Unknown diary event")
    meeting.diary_event_id = body.diary_event_id
    meeting.needs_review = False
    db.commit()
    return {"meeting_id": meeting.id, "diary_event_id": meeting.diary_event_id}
