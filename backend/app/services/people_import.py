"""Bulk-import people from CSV: name,email,team,role,is_bpm,aliases (aliases ;-separated)."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Person, PersonAlias

TRUTHY = {"true", "yes", "y", "1"}

HEADER_ALIASES = {
    "name": ["name", "full name", "person"],
    "email": ["email", "e-mail", "mail"],
    "team": ["team", "department"],
    "role": ["role", "title", "job title"],
    "is_bpm": ["is_bpm", "bpm", "business manager"],
    "aliases": ["aliases", "alias", "also known as"],
}


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    lowered = [h.strip().lower() for h in headers]
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field] = lowered.index(alias)
                break
    return mapping


def _existing_person(db: Session, name: str) -> Person | None:
    lowered = name.lower()
    person = db.query(Person).filter(func.lower(Person.name) == lowered).first()
    if person:
        return person
    alias = db.query(PersonAlias).filter(func.lower(PersonAlias.alias) == lowered).first()
    return alias.person if alias else None


def preview_people(db: Session, rows: list[list[str]]) -> dict:
    if not rows:
        return {"items": [], "skipped": 0}
    mapping = _map_headers(rows[0])
    if "name" not in mapping:
        raise ValueError("Could not find a name column (expected: name / full name / person)")
    items, skipped = [], 0
    seen_in_file: set[str] = set()
    for row in rows[1:]:
        def cell(field: str) -> str:
            index = mapping.get(field)
            return row[index].strip() if index is not None and index < len(row) else ""

        name = cell("name")
        if not name or name.lower() in seen_in_file:
            skipped += 1
            continue
        seen_in_file.add(name.lower())
        existing = _existing_person(db, name)
        items.append(
            {
                "name": name,
                "email": cell("email") or None,
                "team": cell("team") or None,
                "role": cell("role") or None,
                "is_bpm": cell("is_bpm").lower() in TRUTHY,
                "aliases": [a.strip() for a in cell("aliases").split(";") if a.strip()],
                "exists": existing is not None,
                "existing_name": existing.name if existing else None,
            }
        )
    return {"items": items, "skipped": skipped}


def commit_people(db: Session, items: list[dict]) -> dict:
    created, skipped_existing, aliases_added = 0, 0, 0
    known_aliases = {alias.lower() for (alias,) in db.query(func.lower(PersonAlias.alias)).all()}
    known_names = {name.lower() for (name,) in db.query(func.lower(Person.name)).all()}
    for item in items:
        existing = _existing_person(db, item["name"])
        if existing:
            person = existing
            skipped_existing += 1
        else:
            person = Person(
                name=item["name"],
                email=item.get("email"),
                team=item.get("team"),
                role=item.get("role"),
                is_bpm=bool(item.get("is_bpm")),
            )
            db.add(person)
            db.flush()
            known_names.add(person.name.lower())
            created += 1
        for alias in item.get("aliases", []):
            lowered = alias.lower()
            if lowered in known_aliases or lowered in known_names:
                continue
            db.add(PersonAlias(alias=alias, person_id=person.id))
            known_aliases.add(lowered)
            aliases_added += 1
        # With autoflush=False, a just-added PersonAlias row is invisible to
        # _existing_person()'s PersonAlias query (and to any other db.query()) until
        # flushed — a later row in this same file whose name matches an alias just
        # registered for an earlier row would otherwise look "new" and create a
        # duplicate Person. Flush per item so every subsequent _existing_person()
        # lookup sees aliases (and the new person) registered so far.
        db.flush()
    db.commit()
    return {"created": created, "skipped_existing": skipped_existing, "aliases_added": aliases_added}
