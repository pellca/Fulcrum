import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import IMPORTS_DIR
from ..db import get_db
from ..models import DiaryEvent, Meeting, Person, PersonAlias
from ..schemas import (
    DiaryCreateMeetingIn,
    DiaryEventOut,
    DiaryPurgeConfirmIn,
    DiaryPurgeIn,
    DiaryPurgePreviewOut,
    DiaryPurgeResultOut,
    LinkSuggestionOut,
    MeetingOut,
)
from ..services.diary_import import import_diary_file, unmatched_attendees
from ..services.diary_match import DiaryLinkConflict, create_meeting_from_event, suggest_links
from ..services.diary_purge import purge_diary_range

router = APIRouter(prefix="/diary", tags=["diary"])


def _validate_date_range(from_date: str, to_date: str) -> None:
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, f"{label} must be in YYYY-MM-DD format")
    if from_date > to_date:
        raise HTTPException(422, "from_date must not be after to_date")


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


@router.get("/link-suggestions", response_model=list[LinkSuggestionOut])
def link_suggestions(limit: int = 25, within_minutes: int = 120, db: Session = Depends(get_db)):
    return suggest_links(db, limit=limit, within_minutes=within_minutes)


@router.post("/create-meeting", response_model=MeetingOut, status_code=201)
def create_meeting(body: DiaryCreateMeetingIn, db: Session = Depends(get_db)):
    try:
        return create_meeting_from_event(db, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except DiaryLinkConflict as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/purge-preview", response_model=DiaryPurgePreviewOut)
def purge_preview(body: DiaryPurgeIn, db: Session = Depends(get_db)):
    _validate_date_range(body.from_date, body.to_date)
    return purge_diary_range(
        db, body.from_date, body.to_date, body.include_cancelled, dry_run=True
    )


@router.post("/purge", response_model=DiaryPurgeResultOut)
def purge(body: DiaryPurgeConfirmIn, db: Session = Depends(get_db)):
    if body.confirm != "DELETE":
        raise HTTPException(422, 'Type "DELETE" to confirm')
    _validate_date_range(body.from_date, body.to_date)
    return purge_diary_range(
        db, body.from_date, body.to_date, body.include_cancelled, dry_run=False
    )
