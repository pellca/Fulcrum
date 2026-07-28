"""Quick-add token parser.

Grammar (tokens may appear anywhere; the rest is the title):
    @owner        person by name/alias fragment, e.g. @sarah or @"Sarah Chen"
    #workstream   workstream by name fragment
    due:VALUE     2026-08-15 | today | tomorrow | +N (days) | mon..sun (next such day)
    !PRIORITY     !high | !med | !medium | !low
    origin:VALUE  principal | aet | external | self   (commitments only)
"""

import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Person, PersonAlias, Workstream

TOKEN_RE = re.compile(
    r"""(@"[^"]+"|@\S+|\#\S+|due:\S+|origin:\S+|!\S+)""",
    re.VERBOSE,
)

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
PRIORITIES = {"high": "high", "med": "medium", "medium": "medium", "low": "low"}
ORIGINS = {"principal", "aet", "external", "self"}


def parse_due(value: str, today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    value = value.lower()
    if value == "today":
        return today
    if value == "tomorrow":
        return today + timedelta(days=1)
    if value.startswith("+") and value[1:].isdigit():
        return today + timedelta(days=int(value[1:]))
    if value[:3] in WEEKDAYS:
        target = WEEKDAYS[value[:3]]
        delta = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=delta)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def find_person(db: Session, fragment: str) -> Optional[Person]:
    frag = fragment.lower()
    exact = (
        db.query(Person).filter(func.lower(Person.name) == frag, Person.active.is_(True)).first()
    )
    if exact:
        return exact
    alias = db.query(PersonAlias).filter(func.lower(PersonAlias.alias) == frag).first()
    if alias:
        return alias.person
    return (
        db.query(Person)
        .filter(Person.name.ilike(f"%{fragment}%"), Person.active.is_(True))
        .order_by(Person.name)
        .first()
    )


def find_workstream(db: Session, fragment: str) -> Optional[Workstream]:
    frag = fragment.lower()
    exact = db.query(Workstream).filter(func.lower(Workstream.name) == frag).first()
    if exact:
        return exact
    return (
        db.query(Workstream)
        .filter(Workstream.name.ilike(f"%{fragment}%"))
        .order_by(Workstream.name)
        .first()
    )


def parse_quickadd(db: Session, text: str, today: Optional[date] = None) -> dict:
    result: dict = {
        "title": "",
        "owner_id": None,
        "owner_name": None,
        "workstream_id": None,
        "workstream_name": None,
        "due_date": None,
        "priority": "medium",
        "origin": None,
        "warnings": [],
    }
    remainder = text
    for token in TOKEN_RE.findall(text):
        remainder = remainder.replace(token, "", 1)
        if token.startswith("@"):
            fragment = token[1:].strip('"')
            person = find_person(db, fragment)
            if person:
                result["owner_id"], result["owner_name"] = person.id, person.name
            else:
                result["warnings"].append(f"No person matching '{fragment}'")
        elif token.startswith("#"):
            fragment = token[1:]
            ws = find_workstream(db, fragment)
            if ws:
                result["workstream_id"], result["workstream_name"] = ws.id, ws.name
            else:
                result["warnings"].append(f"No workstream matching '{fragment}'")
        elif token.startswith("due:"):
            due = parse_due(token[4:], today)
            if due:
                result["due_date"] = due
            else:
                result["warnings"].append(f"Could not parse date '{token[4:]}'")
        elif token.startswith("origin:"):
            value = token[7:].lower()
            if value in ORIGINS:
                result["origin"] = value
            else:
                result["warnings"].append(f"Unknown origin '{value}'")
        elif token.startswith("!"):
            priority = PRIORITIES.get(token[1:].lower())
            if priority:
                result["priority"] = priority
            else:
                result["warnings"].append(f"Unknown priority '{token[1:]}'")
    result["title"] = " ".join(remainder.split())
    return result
