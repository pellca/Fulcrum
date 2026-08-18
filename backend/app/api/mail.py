import difflib
import json
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..config import IMPORTS_DIR
from ..db import get_db
from ..models import Action, Chase, Commitment, Link, MailMessage, Person, PersonAlias, PersonNote
from ..models._mixins import utcnow
from ..schemas import (
    CloseActionFromMailIn,
    CloseActionFromMailOut,
    CreateActionFromMailIn,
    CreateActionFromMailOut,
    DismissBulkIn,
    DismissBulkOut,
    LogChaseIn,
    LogChaseOut,
    PersonNoteFromMailIn,
    PersonNoteOut,
    SuggestionsOut,
    TriageOut,
)
from ..services.chase import latest_chase_map
from ..services.mail_import import import_mail_file
from ..services.quickadd import parse_quickadd

router = APIRouter(prefix="/mail", tags=["mail"])

MAX_DAYS = 5
STATS_TRIAGE_STATES = ("pending", "linked", "dismissed")


def _now_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def _get_mail(db: Session, mail_id: int) -> MailMessage:
    mail = db.get(MailMessage, mail_id)
    if not mail:
        raise HTTPException(404, "Mail message not found")
    return mail


def _parse_occurred_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _recipient_emails(message: MailMessage) -> list[str]:
    emails = []
    for recipient in list(message.to_recipients or []) + list(message.cc_recipients or []):
        email = recipient.get("email") if isinstance(recipient, dict) else None
        if email:
            emails.append(email.strip().lower())
    return emails


def _build_person_map(db: Session, messages: list[MailMessage]) -> dict[str, Person]:
    """Batch resolve every sender/recipient address across `messages` to a Person
    in two queries total (one on Person.email, one on PersonAlias with the
    matching Person eager-loaded), instead of one resolve_email() round trip
    per address."""
    emails: set[str] = set()
    for message in messages:
        if message.sender_email:
            emails.add(message.sender_email.strip().lower())
        emails.update(_recipient_emails(message))
    if not emails:
        return {}

    person_map: dict[str, Person] = {}
    for person in db.query(Person).filter(func.lower(Person.email).in_(emails)):
        if person.email:
            person_map.setdefault(person.email.strip().lower(), person)

    remaining = emails - set(person_map)
    if remaining:
        aliases = (
            db.query(PersonAlias)
            .options(joinedload(PersonAlias.person))
            .filter(func.lower(PersonAlias.alias).in_(remaining))
            .all()
        )
        for alias in aliases:
            if alias.person is not None:
                person_map[alias.alias.strip().lower()] = alias.person
    return person_map


def _serialize(message: MailMessage, person_map: dict[str, Person]) -> dict:
    sender_email = message.sender_email.strip().lower() if message.sender_email else None
    sender_person = person_map.get(sender_email) if sender_email else None

    matched: dict[int, dict] = {}
    for email in _recipient_emails(message):
        person = person_map.get(email)
        if person and person.id not in matched:
            # matched_email is the (lowercased) address that actually resolved to
            # this person, which differs from person.email on alias matches — the
            # frontend needs it to know which chip to attach to which recipient.
            matched[person.id] = {
                "id": person.id,
                "name": person.name,
                "email": person.email,
                "matched_email": email,
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
    person_map = _build_person_map(db, rows)
    return [_serialize(row, person_map) for row in rows]


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


# ---------- triage verbs & suggestions ----------


@router.get("/{mail_id}/suggestions", response_model=SuggestionsOut)
def suggestions(mail_id: int, db: Session = Depends(get_db)):
    mail = _get_mail(db, mail_id)
    today = date.today()

    person_map = _build_person_map(db, [mail])
    sender_email = mail.sender_email.strip().lower() if mail.sender_email else None
    sender_person = person_map.get(sender_email) if sender_email else None
    recipient_ids = {
        person.id for email in _recipient_emails(mail) if (person := person_map.get(email))
    }

    latest_chases = latest_chase_map(db)
    subject = (mail.subject or "").lower()

    candidates: list[tuple[str, Action | Commitment]] = [
        ("action", row)
        for row in db.query(Action)
        .options(joinedload(Action.owner))
        .filter(Action.status.notin_(["done", "cancelled"]))
    ] + [
        ("commitment", row)
        for row in db.query(Commitment)
        .options(joinedload(Commitment.owner))
        .filter(Commitment.status.notin_(["delivered", "dropped"]))
    ]

    scored = []
    for kind, item in candidates:
        score = 0.0
        reasons: list[str] = []
        owner = item.owner

        if owner is not None:
            if mail.folder == "inbox" and sender_person is not None and owner.id == sender_person.id:
                score += 3.0
                reasons.append(f"Owned by {owner.name} (sender)")
            if mail.folder == "sent" and owner.id in recipient_ids:
                score += 3.0
                reasons.append(f"Sent to owner {owner.name}")
            if mail.folder == "inbox" and owner.id in recipient_ids:
                score += 2.0
                reasons.append(f"Also addressed to owner {owner.name}")

        chase = latest_chases.get((kind, item.id))
        if chase is not None and chase.next_chase_on is not None and chase.next_chase_on <= today:
            score += 2.0
            reasons.append("Chase due")

        if item.due_date is not None and (item.due_date - today).days <= 7:
            score += 1.0
            reasons.append("Overdue" if item.due_date < today else f"Due {item.due_date.isoformat()}")

        ratio = difflib.SequenceMatcher(None, subject, item.title.lower()).ratio()
        if ratio >= 0.35:
            score += round(3 * ratio, 2)
            reasons.append("Title similar to subject")

        if score <= 0:
            continue

        scored.append(
            {
                "type": kind,
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "due_date": item.due_date,
                "owner": {"id": owner.id, "name": owner.name} if owner else None,
                "score": round(score, 2),
                "reasons": reasons,
            }
        )

    scored.sort(key=lambda s: (-s["score"], s["due_date"] is None, s["due_date"] or date.max))
    return {"suggestions": scored[:6]}


@router.post("/{mail_id}/log-chase", response_model=LogChaseOut)
def log_chase(mail_id: int, body: LogChaseIn, db: Session = Depends(get_db)):
    mail = _get_mail(db, mail_id)
    if body.target_type == "action":
        target = db.get(Action, body.target_id)
    else:
        target = db.get(Commitment, body.target_id)
    if not target:
        raise HTTPException(404, f"{body.target_type.capitalize()} not found")

    chased_on = _parse_occurred_date(mail.occurred_date) or date.today()
    chase = Chase(
        action_id=body.target_id if body.target_type == "action" else None,
        commitment_id=body.target_id if body.target_type == "commitment" else None,
        chased_on=chased_on,
        method="email",
        note=body.note or f"Chased via email: {mail.subject}",
        next_chase_on=body.next_chase_on,
    )
    db.add(chase)
    db.add(
        Link(
            from_type="mail",
            from_id=mail.id,
            to_type=body.target_type,
            to_id=body.target_id,
            kind="informs",
            rationale="Chase logged from email",
        )
    )
    mail.triage = "linked"
    mail.triaged_at = _now_iso()
    db.commit()
    return {"chase_id": chase.id, "target_type": body.target_type, "target_id": body.target_id}


@router.post("/{mail_id}/create-action", response_model=CreateActionFromMailOut)
def create_action_from_mail(
    mail_id: int, body: CreateActionFromMailIn, db: Session = Depends(get_db)
):
    mail = _get_mail(db, mail_id)
    parsed = parse_quickadd(db, body.text)
    if not parsed["title"]:
        raise HTTPException(422, "No title after removing tokens")

    action = Action(
        title=parsed["title"],
        owner_id=parsed["owner_id"],
        workstream_id=parsed["workstream_id"],
        due_date=parsed["due_date"],
        priority=parsed["priority"],
    )
    db.add(action)
    db.flush()
    db.add(
        Link(
            from_type="mail",
            from_id=mail.id,
            to_type="action",
            to_id=action.id,
            kind="informs",
            rationale="Created from email",
        )
    )
    mail.triage = "linked"
    mail.triaged_at = _now_iso()
    db.commit()
    return {
        "action_id": action.id,
        "title": action.title,
        "owner_name": parsed["owner_name"],
        "due_date": action.due_date,
        "warnings": parsed["warnings"],
    }


@router.post("/{mail_id}/close-action", response_model=CloseActionFromMailOut)
def close_action_from_mail(
    mail_id: int, body: CloseActionFromMailIn, db: Session = Depends(get_db)
):
    mail = _get_mail(db, mail_id)
    action = db.get(Action, body.action_id)
    if not action:
        raise HTTPException(404, "Action not found")

    action.status = "done"
    db.add(
        Link(
            from_type="mail",
            from_id=mail.id,
            to_type="action",
            to_id=action.id,
            kind="informs",
            rationale="Closed with evidence from email",
        )
    )
    mail.triage = "linked"
    mail.triaged_at = _now_iso()
    db.commit()
    return {"action_id": action.id, "status": action.status}


@router.post("/{mail_id}/person-note", response_model=PersonNoteOut)
def person_note_from_mail(
    mail_id: int, body: PersonNoteFromMailIn, db: Session = Depends(get_db)
):
    mail = _get_mail(db, mail_id)
    person = db.get(Person, body.person_id)
    if not person:
        raise HTTPException(404, "Person not found")

    note_text = (body.note or "").strip()
    if not note_text:
        raise HTTPException(422, "Note is required")

    note = PersonNote(
        person_id=body.person_id,
        kind=body.kind,
        note=note_text,
        noted_on=date.today(),
        source="mail",
    )
    db.add(note)
    db.flush()
    db.add(
        Link(
            from_type="mail",
            from_id=mail.id,
            to_type="person_note",
            to_id=note.id,
            kind="relates",
            rationale="Noted from email",
        )
    )
    mail.triage = "linked"
    mail.triaged_at = _now_iso()
    db.commit()
    return note


@router.post("/{mail_id}/dismiss", response_model=TriageOut)
def dismiss_mail(mail_id: int, db: Session = Depends(get_db)):
    mail = _get_mail(db, mail_id)
    mail.triage = "dismissed"
    mail.triaged_at = _now_iso()
    db.commit()
    return {"triage": mail.triage}


@router.post("/{mail_id}/reopen", response_model=TriageOut)
def reopen_mail(mail_id: int, db: Session = Depends(get_db)):
    mail = _get_mail(db, mail_id)
    mail.triage = "pending"
    mail.triaged_at = None
    db.commit()
    return {"triage": mail.triage}


@router.post("/dismiss-bulk", response_model=DismissBulkOut)
def dismiss_bulk(body: DismissBulkIn, db: Session = Depends(get_db)):
    rows = (
        db.query(MailMessage)
        .filter(MailMessage.id.in_(body.ids), MailMessage.triage == "pending")
        .all()
    )
    now = _now_iso()
    for row in rows:
        row.triage = "dismissed"
        row.triaged_at = now
    db.commit()
    return {"dismissed": len(rows)}
