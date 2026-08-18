from datetime import date


def _make_person(client, name="Jamie Fox"):
    return client.post("/api/people", json={"name": name}).json()


def test_create_note_defaults_noted_on_to_today(client):
    person = _make_person(client)
    note = client.post(
        f"/api/people/{person['id']}/notes", json={"note": "Good work on the audit scope."}
    ).json()
    assert note["noted_on"] == date.today().isoformat()
    assert note["kind"] == "general"
    assert note["source"] == "manual"
    assert note["discussed_on"] is None
    assert note["person_id"] == person["id"]


def test_create_note_explicit_noted_on(client):
    person = _make_person(client)
    note = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Raised a concern on call.", "kind": "call", "noted_on": "2026-01-05"},
    ).json()
    assert note["noted_on"] == "2026-01-05"
    assert note["kind"] == "call"


def test_list_notes_newest_first(client):
    person = _make_person(client)
    n1 = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "First", "noted_on": "2026-01-01"},
    ).json()
    n2 = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Second", "noted_on": "2026-01-10"},
    ).json()
    n3 = client.post(
        f"/api/people/{person['id']}/notes",
        json={"note": "Third same day a", "noted_on": "2026-01-10"},
    ).json()
    notes = client.get(f"/api/people/{person['id']}/notes").json()
    ids = [n["id"] for n in notes]
    # newest noted_on first; ties broken by id desc
    assert ids == [n3["id"], n2["id"], n1["id"]]


def test_kind_filter(client):
    person = _make_person(client)
    client.post(f"/api/people/{person['id']}/notes", json={"note": "General note"})
    call_note = client.post(
        f"/api/people/{person['id']}/notes", json={"note": "Call note", "kind": "call"}
    ).json()

    filtered = client.get(f"/api/people/{person['id']}/notes", params={"kind": "call"}).json()
    assert [n["id"] for n in filtered] == [call_note["id"]]


def test_undiscussed_filter(client):
    person = _make_person(client)
    note = client.post(f"/api/people/{person['id']}/notes", json={"note": "Needs a chat"}).json()

    undiscussed = client.get(
        f"/api/people/{person['id']}/notes", params={"undiscussed": True}
    ).json()
    assert [n["id"] for n in undiscussed] == [note["id"]]

    client.patch(f"/api/people/notes/{note['id']}", json={"discussed_on": "2026-08-18"})

    undiscussed_after = client.get(
        f"/api/people/{person['id']}/notes", params={"undiscussed": True}
    ).json()
    assert undiscussed_after == []


def test_patch_and_delete_note(client):
    person = _make_person(client)
    note = client.post(f"/api/people/{person['id']}/notes", json={"note": "Original"}).json()

    updated = client.patch(f"/api/people/notes/{note['id']}", json={"note": "Updated text"}).json()
    assert updated["note"] == "Updated text"

    assert client.delete(f"/api/people/notes/{note['id']}").status_code == 204
    assert client.get(f"/api/people/{person['id']}/notes").json() == []
    # idempotent delete
    assert client.delete(f"/api/people/notes/{note['id']}").status_code == 204


def test_patch_unknown_note_404(client):
    assert client.patch("/api/people/notes/99999", json={"note": "x"}).status_code == 404


def test_404_on_unknown_person_for_list_and_create(client):
    assert client.get("/api/people/99999/notes").status_code == 404
    assert client.post("/api/people/99999/notes", json={"note": "x"}).status_code == 404


def test_person_delete_cascades_notes(client):
    person = _make_person(client)
    client.post(f"/api/people/{person['id']}/notes", json={"note": "Will be cascaded"})

    assert client.delete(f"/api/people/{person['id']}").status_code == 204
    # notes gone at the DB level (SQLite FK cascade); listing now 404s since person is gone
    assert client.get(f"/api/people/{person['id']}/notes").status_code == 404


def test_person_references_includes_notes_count(client):
    person = _make_person(client)
    client.post(f"/api/people/{person['id']}/notes", json={"note": "One"})
    client.post(f"/api/people/{person['id']}/notes", json={"note": "Two"})

    refs = client.get(f"/api/people/{person['id']}/references").json()
    labels = {w["label"]: w for w in refs["warnings"]}
    assert labels["notes recorded"]["count"] == 2
