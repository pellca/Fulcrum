import json
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import IMPORTS_DIR
from ..db import get_db
from ..models import MailMessage
from ..services.mail_import import import_mail_file, resolve_email

router = APIRouter(prefix="/mail", tags=["mail"])

MAX_DAYS = 5
STATS_TRIAGE_STATES = ("pending", "linked", "dismissed")


def _serialize(message: MailMessage, db: Session) -> dict:
    sender_person = resolve_email(db, message.sender_email)

    matched: dict[int, dict] = {}
    for recipient in list(message.to_recipients or []) + list(message.cc_recipients or []):
        email = recipient.get("email") if isinstance(recipient, dict) else None
        person = resolve_email(db, email)
        if person and person.id not in matched:
            # matched_email is the (lowercased) address that actually resolved to
            # this person, which differs from person.email on alias matches — the
            # frontend needs it to know which chip to attach to which recipient.
            matched[person.id] = {
                "id": person.id,
                "name": person.name,
                "email": person.email,
                "matched_email": email.strip().lower(),
            }

    return {
        "id": message.id,
        "message_id": message.message_id,
        "conversation_id": message.conversation_id,
        "folder": message.folder,
        "subject": message.subject,
        "sender_name": message.sender_name,
        "sender_email": message.sender_email,
        "to_recipients": message.to_recipients,
        "cc_recipients": message.cc_recipients,
        "sent_at": message.sent_at,
        "received_at": message.received_at,
        "occurred_date": message.occurred_date,
        "body_text": message.body_text,
        "has_attachments": message.has_attachments,
        "triage": message.triage,
        "triaged_at": message.triaged_at,
        "sender_person": {"id": sender_person.id, "name": sender_person.name}
        if sender_person
        else None,
        "matched_people": list(matched.values()),
    }


@router.get("/messages")
def list_messages(
    days: int = MAX_DAYS,
    folder: str | None = None,
    triage: str | None = None,
    db: Session = Depends(get_db),
):
    days = max(1, min(MAX_DAYS, days))
    since = (date.today() - timedelta(days=days - 1)).isoformat()

    query = db.query(MailMessage).filter(MailMessage.occurred_date >= since)
    if folder:
        query = query.filter(MailMessage.folder == folder)
    if triage:
        query = query.filter(MailMessage.triage == triage)
    # sent items carry no received_at, so fall back to sent_at for the intra-day
    # ordering — otherwise every sent row ties on NULL and comes back unordered
    query = query.order_by(
        MailMessage.occurred_date.desc(),
        func.coalesce(MailMessage.received_at, MailMessage.sent_at).desc(),
    )

    rows = query.limit(500).all()
    return [_serialize(row, db) for row in rows]


class ImportPathIn(BaseModel):
    path: str


@router.post("/import")
def import_from_path(body: ImportPathIn, db: Session = Depends(get_db)):
    try:
        return import_mail_file(db, body.path)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {body.path}")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/import-upload")
async def import_from_upload(file: UploadFile, db: Session = Depends(get_db)):
    destination = IMPORTS_DIR / f"mailbox-{int(time.time())}.json"
    destination.write_bytes(await file.read())
    try:
        return import_mail_file(db, destination)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    since = (date.today() - timedelta(days=MAX_DAYS - 1)).isoformat()
    rows = (
        db.query(MailMessage.triage, func.count(MailMessage.id))
        .filter(MailMessage.occurred_date >= since)
        .group_by(MailMessage.triage)
        .all()
    )
    raw_counts = {triage_value: count for triage_value, count in rows}
    counts = {state: raw_counts.get(state, 0) for state in STATS_TRIAGE_STATES}
    # an unexpected triage value (shouldn't happen, but must never 500) still
    # contributes to total — it just doesn't get its own key in the response
    counts["total"] = sum(raw_counts.values())
    return counts
