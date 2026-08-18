from datetime import date

from app.models import Person
from app.services.quickadd import parse_quickadd

TODAY = date(2026, 8, 18)


def _make_person(client, name="Priya Nair"):
    return client.post("/api/people", json={"name": name}).json()


# ---------- parser ----------


def test_parse_quickadd_kind_token(db):
    person = Person(name="Priya Nair")
    db.add(person)
    db.commit()

    result = parse_quickadd(db, "handled it well @priya kind:feedback", TODAY)
    assert result["kind"] == "feedback"
    assert result["owner_id"] == person.id
    assert result["title"] == "handled it well"
    assert result["warnings"] == []


def test_parse_quickadd_unknown_kind_warns(db):
    person = Person(name="Priya Nair")
    db.add(person)
    db.commit()

    result = parse_quickadd(db, "some note @priya kind:sarcasm", TODAY)
    assert result["kind"] is None
    assert any("Unknown note kind 'sarcasm'" in w for w in result["warnings"])


def test_quickadd_preview_surfaces_kind(client):
    _make_person(client, "Priya Nair")
    preview = client.post(
        "/api/quickadd/preview", json={"text": "handled it well @priya kind:feedback"}
    ).json()
    assert preview["kind"] == "feedback"


def test_quickadd_preview_kind_none_when_absent(client):
    _make_person(client, "Priya Nair")
    preview = client.post("/api/quickadd/preview", json={"text": "no kind here @priya"}).json()
    assert preview["kind"] is None


# ---------- quickadd note creation ----------


def test_quickadd_note_creates_person_note(client):
    person = _make_person(client, "Sarah Chen")
    res = client.post(
        "/api/quickadd",
        json={"text": "handled it well @sarah kind:feedback", "type": "note"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["type"] == "note"
    assert body["title"] == "handled it well"
    assert body["warnings"] == []

    notes = client.get(f"/api/people/{person['id']}/notes").json()
    assert len(notes) == 1
    assert notes[0]["note"] == "handled it well"
    assert notes[0]["kind"] == "feedback"
    assert notes[0]["person_id"] == person["id"]
    assert notes[0]["noted_on"] == date.today().isoformat()
    assert notes[0]["source"] == "manual"


def test_quickadd_note_defaults_kind_general(client):
    person = _make_person(client, "Sarah Chen")
    client.post("/api/quickadd", json={"text": "quick chat @sarah", "type": "note"})

    notes = client.get(f"/api/people/{person['id']}/notes").json()
    assert notes[0]["kind"] == "general"


def test_quickadd_note_without_matching_person_422(client):
    res = client.post(
        "/api/quickadd", json={"text": "handled it well @nobody kind:feedback", "type": "note"}
    )
    assert res.status_code == 422


# ---------- 1:1 pack ----------


def test_pack_notes_section_undiscussed_newest_first(client):
    person = _make_person(client, "Priya Nair")
    n1 = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Older", "noted_on": "2026-01-01"},
    ).json()
    n2 = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Newer", "noted_on": "2026-01-10"},
    ).json()
    discussed = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Already discussed", "noted_on": "2026-01-15"},
    ).json()
    client.patch(f"/api/people/notes/{discussed['id']}", json={"discussed_on": "2026-01-16"})

    pack = client.get(f"/api/people/{person['id']}/pack").json()
    ids = [n["id"] for n in pack["notes"]]
    assert ids == [n2["id"], n1["id"]]
    assert pack["notes"][0]["note"] == "Newer"
    assert pack["notes"][0]["kind"] == "general"
    assert pack["notes"][0]["source"] == "manual"


# ---------- mark-discussed ----------


def test_mark_discussed_all_variant(client):
    person = _make_person(client, "Priya Nair")
    client.post(f"/api/people/{person['id']}/notes", json={"note": "One"})
    client.post(f"/api/people/{person['id']}/notes", json={"note": "Two"})

    res = client.post(f"/api/people/{person['id']}/notes/mark-discussed")
    assert res.status_code == 200
    assert res.json() == {"marked": 2}

    notes = client.get(f"/api/people/{person['id']}/notes").json()
    assert all(n["discussed_on"] == date.today().isoformat() for n in notes)

    pack = client.get(f"/api/people/{person['id']}/pack").json()
    assert pack["notes"] == []


def test_mark_discussed_ids_subset_variant(client):
    person = _make_person(client, "Priya Nair")
    n1 = client.post(f"/api/people/{person['id']}/notes", json={"note": "One"}).json()
    n2 = client.post(f"/api/people/{person['id']}/notes", json={"note": "Two"}).json()

    res = client.post(
        f"/api/people/{person['id']}/notes/mark-discussed", json={"ids": [n1["id"]]}
    )
    assert res.json() == {"marked": 1}

    notes = {n["id"]: n for n in client.get(f"/api/people/{person['id']}/notes").json()}
    assert notes[n1["id"]]["discussed_on"] == date.today().isoformat()
    assert notes[n2["id"]]["discussed_on"] is None

    pack = client.get(f"/api/people/{person['id']}/pack").json()
    assert [n["id"] for n in pack["notes"]] == [n2["id"]]


def test_mark_discussed_empty_ids_marks_nothing(client):
    person = _make_person(client, "Priya Nair")
    client.post(f"/api/people/{person['id']}/notes", json={"note": "One"})

    res = client.post(f"/api/people/{person['id']}/notes/mark-discussed", json={"ids": []})
    assert res.json() == {"marked": 0}

    notes = client.get(f"/api/people/{person['id']}/notes").json()
    assert notes[0]["discussed_on"] is None


def test_mark_discussed_unknown_person_404(client):
    assert client.post("/api/people/99999/notes/mark-discussed").status_code == 404
