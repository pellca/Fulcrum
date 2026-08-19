"""Tests for backend/app/services/people_import.py's commit_people/preview_people."""

from app.models import Person, PersonAlias
from app.services.people_import import commit_people, preview_people


def test_alias_registered_by_earlier_row_is_seen_by_later_row(db):
    """F4 regression: with autoflush=False, a PersonAlias added for one row was
    invisible to _existing_person()'s PersonAlias query until the session flushed —
    so a later row in the same file whose name matched an alias just registered for
    an earlier row looked "new" and created a duplicate Person instead of being
    recognised as the same person. commit_people must flush after each item's alias
    rows so every subsequent lookup sees them."""
    rows = [
        ["name", "email", "aliases"],
        ["Robert Smith", "rs@bank.com", "Bob Smith;RS"],
        ["Bob Smith", "bob@bank.com", ""],
    ]
    preview = preview_people(db, rows)
    result = commit_people(db, preview["items"])

    assert result == {"created": 1, "skipped_existing": 1, "aliases_added": 2}

    people = db.query(Person).all()
    assert len(people) == 1
    assert people[0].name == "Robert Smith"

    aliases = {a.alias: a.person_id for a in db.query(PersonAlias).all()}
    assert aliases == {"Bob Smith": people[0].id, "RS": people[0].id}
