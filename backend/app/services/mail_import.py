"""Import a mailbox.json produced by the mail extractor (tools/mail_extractor).

The extractor guarantees: each file is the FULL current window (no deltas), so
import is an idempotent upsert by message `id`. Content fields are refreshed on
every import; `triage`/`triaged_at` are user state and are always preserved.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import MAIL_RETENTION_DAYS
from ..models import Link, MailMessage, Person, PersonAlias
from .import_utils import dedupe_by_id

SUPPORTED_VERSION = 1


def _date_only(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else None


def _occurred_date(folder: str | None, sent_at: str | None, received_at: str | None) -> str | None:
    if folder == "sent":
        primary, fallback = sent_at, received_at
    else:
        primary, fallback = received_at, sent_at
    return _date_only(primary) or _date_only(fallback)


def import_mailbox(db: Session, data: dict) -> dict:
    if not isinstance(data, dict) or "messages" not in data:
        raise ValueError("Not a mailbox.json file: missing 'messages' key")
    messages = data["messages"]
    if not isinstance(messages, list):
        raise ValueError("Not a mailbox.json file: 'messages' must be a list")

    meta = data.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    version = meta.get("version")
    if version is not None and version != SUPPORTED_VERSION:
        raise ValueError(f"Unsupported mailbox.json version: {version!r}")

    for raw in messages:
        if not isinstance(raw, dict):
            raise ValueError(f"Malformed message entry: expected an object, got {type(raw).__name__}")

    messages, duplicates = dedupe_by_id(messages)

    counts = {"added": 0, "updated": 0}
    for raw in messages:
        message_id = raw.get("id")
        if not message_id:
            continue
        folder = raw.get("folder") or "inbox"
        sent_at = raw.get("sent_at")
        received_at = raw.get("received_at")
        fields = dict(
            conversation_id=raw.get("conversation_id"),
            folder=folder,
            subject=raw.get("subject"),
            sender_name=raw.get("sender_name"),
            sender_email=raw.get("sender_email"),
            to_recipients=raw.get("to") or [],
            cc_recipients=raw.get("cc") or [],
            sent_at=sent_at,
            received_at=received_at,
            occurred_date=_occurred_date(folder, sent_at, received_at),
            body_text=raw.get("body_text"),
            has_attachments=bool(raw.get("has_attachments")),
            raw=raw,
        )
        row = db.query(MailMessage).filter(MailMessage.message_id == message_id).first()
        if row is None:
            db.add(MailMessage(message_id=message_id, **fields))
            counts["added"] += 1
        else:
            for key, value in fields.items():
                setattr(row, key, value)
            counts["updated"] += 1
    db.flush()

    purged = _purge_retention(db)
    db.commit()

    return {**counts, "duplicates": duplicates, "purged": purged}


def import_mail_file(db: Session, path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return import_mailbox(db, payload)


def _purge_retention(db: Session) -> int:
    cutoff = (date.today() - timedelta(days=MAIL_RETENTION_DAYS)).isoformat()
    # A row with no occurred_date (neither sent_at nor received_at was readable)
    # can never satisfy the day-window filter, so it is invisible in the UI; if
    # it were also excluded here it would live forever. Purge it with the same
    # triage/link protection as an out-of-retention row.
    candidates = (
        db.query(MailMessage)
        .filter(
            or_(MailMessage.occurred_date.is_(None), MailMessage.occurred_date < cutoff),
            MailMessage.triage != "linked",
        )
        .all()
    )
    if not candidates:
        return 0

    linked_ids: set[int] = set()
    for link in db.query(Link).filter(or_(Link.from_type == "mail", Link.to_type == "mail")).all():
        if link.from_type == "mail":
            linked_ids.add(link.from_id)
        if link.to_type == "mail":
            linked_ids.add(link.to_id)

    purged = 0
    for row in candidates:
        if row.id in linked_ids:
            continue
        db.delete(row)
        purged += 1
    return purged


def resolve_email(db: Session, email: str | None) -> Person | None:
    """Case-insensitive Person lookup by email, falling back to PersonAlias."""
    if not email:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    person = db.query(Person).filter(func.lower(Person.email) == normalized).first()
    if person:
        return person
    alias = db.query(PersonAlias).filter(func.lower(PersonAlias.alias) == normalized).first()
    if alias:
        return db.get(Person, alias.person_id)
    return None
