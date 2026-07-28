from datetime import date

from app.models import Person, PersonAlias, Workstream
from app.services.quickadd import parse_due, parse_quickadd

TODAY = date(2026, 7, 28)  # a Tuesday


def test_parse_due_variants():
    assert parse_due("2026-08-15", TODAY) == date(2026, 8, 15)
    assert parse_due("today", TODAY) == TODAY
    assert parse_due("tomorrow", TODAY) == date(2026, 7, 29)
    assert parse_due("+7", TODAY) == date(2026, 8, 4)
    assert parse_due("fri", TODAY) == date(2026, 7, 31)
    assert parse_due("tue", TODAY) == date(2026, 8, 4)  # next Tuesday, not today
    assert parse_due("nonsense", TODAY) is None


def test_parse_quickadd_full(db):
    person = Person(name="Sarah Chen")
    ws = Workstream(name="Credit Risk Audit")
    db.add_all([person, ws])
    db.commit()

    result = parse_quickadd(db, "Chase scope pack @sarah #credit due:fri !high", TODAY)
    assert result["title"] == "Chase scope pack"
    assert result["owner_id"] == person.id
    assert result["workstream_id"] == ws.id
    assert result["due_date"] == date(2026, 7, 31)
    assert result["priority"] == "high"
    assert result["warnings"] == []


def test_parse_quickadd_alias_and_warnings(db):
    person = Person(name="James Whitfield")
    db.add(person)
    db.flush()
    db.add(PersonAlias(alias="jw", person_id=person.id))
    db.commit()

    result = parse_quickadd(db, "Weekly note @jw due:banana", TODAY)
    assert result["owner_id"] == person.id
    assert result["due_date"] is None
    assert any("banana" in w for w in result["warnings"])


def test_parse_quickadd_quoted_name(db):
    db.add(Person(name="Lena Kovacs"))
    db.commit()
    result = parse_quickadd(db, 'Review pack @"Lena Kovacs" !med', TODAY)
    assert result["owner_name"] == "Lena Kovacs"
    assert result["priority"] == "medium"
    assert result["title"] == "Review pack"
