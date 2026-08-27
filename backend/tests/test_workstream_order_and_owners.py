"""Workstream display order, and the many-to-many owners/sponsors that replaced
the single owner_id/sponsor_id columns."""

from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import AgendaItem, Forum, Meeting, Person, Topic, Workstream


def _person(client, name):
    return client.post("/api/people", json={"name": name}).json()


def _workstream(client, name, **body):
    resp = client.post("/api/workstreams", json={"name": name, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- ordering ----------


def test_new_workstreams_append_rather_than_tie_for_first(client):
    first = _workstream(client, "First")
    second = _workstream(client, "Second")
    assert first["sort_order"] == 1
    assert second["sort_order"] == 2


def test_explicit_sort_order_is_honoured_on_create(client):
    ws = _workstream(client, "Pinned", sort_order=99)
    assert ws["sort_order"] == 99


def test_reorder_renumbers_to_one_through_n(client):
    a = _workstream(client, "Alpha")
    b = _workstream(client, "Bravo")
    c = _workstream(client, "Charlie")

    resp = client.post("/api/workstreams/reorder", json={"ids": [c["id"], a["id"], b["id"]]})
    assert resp.status_code == 200
    assert [(w["name"], w["sort_order"]) for w in resp.json()] == [
        ("Charlie", 1),
        ("Alpha", 2),
        ("Bravo", 3),
    ]
    # and the plain list agrees, so the order is not just a quirk of the response
    assert [w["name"] for w in client.get("/api/workstreams").json()] == ["Charlie", "Alpha", "Bravo"]


def test_reorder_leaves_ids_it_was_not_given_alone(client):
    """The default list hides closed workstreams, so a drag can only ever send a
    subset — anything off-screen must keep the number it already had."""
    a = _workstream(client, "Alpha")
    b = _workstream(client, "Bravo")
    hidden = _workstream(client, "Hidden", status="closed", sort_order=50)

    client.post("/api/workstreams/reorder", json={"ids": [b["id"], a["id"]]})

    by_name = {w["name"]: w for w in client.get("/api/workstreams?include_closed=true").json()}
    assert by_name["Bravo"]["sort_order"] == 1
    assert by_name["Alpha"]["sort_order"] == 2
    assert by_name["Hidden"]["sort_order"] == 50
    assert hidden["sort_order"] == 50


def test_untouched_workstreams_keep_the_old_category_name_order(client):
    """sort_order 0 means "never ordered by hand" — those rows must still come out
    in the category/name order that predates the column."""
    session = SessionLocal()
    try:
        session.add_all([
            Workstream(name="Zulu", category="audit"),
            Workstream(name="Alpha", category="governance"),
            Workstream(name="Mike", category="audit"),
        ])
        session.commit()
    finally:
        session.close()

    assert [w["name"] for w in client.get("/api/workstreams").json()] == ["Mike", "Zulu", "Alpha"]


def test_rolling_agenda_bands_follow_sort_order(client):
    session = SessionLocal()
    try:
        forum = Forum(name="ExCo", capacity_minutes=60)
        session.add(forum)
        session.flush()
        forum_id = forum.id
        meeting = Meeting(forum_id=forum_id, scheduled_at=datetime.now() + timedelta(days=1))
        session.add(meeting)
        # deliberately reverse-alphabetical against the order they should come out in
        last = Workstream(name="Alpha", category="audit", sort_order=9)
        first = Workstream(name="Zulu", category="audit", sort_order=1)
        session.add_all([last, first])
        session.flush()
        for index, ws in enumerate([last, first]):
            topic = Topic(title=f"Topic {index}", workstream_id=ws.id)
            session.add(topic)
            session.flush()
            session.add(AgendaItem(meeting_id=meeting.id, topic_id=topic.id, sequence=index + 1))
        session.commit()
    finally:
        session.close()

    body = client.get(f"/api/forums/{forum_id}/rolling-agenda").json()
    assert [band["label"] for band in body["bands"]] == ["Zulu", "Alpha"]


# ---------- multiple owners ----------


def test_workstream_round_trips_several_owners(client):
    lena = _person(client, "Lena Kovacs")
    priya = _person(client, "Priya Shah")

    ws = _workstream(client, "S166 Response", owner_ids=[lena["id"], priya["id"]])
    assert [o["name"] for o in ws["owners"]] == ["Lena Kovacs", "Priya Shah"]

    patched = client.patch(f"/api/workstreams/{ws['id']}", json={"owner_ids": [priya["id"]]}).json()
    assert [o["name"] for o in patched["owners"]] == ["Priya Shah"]

    cleared = client.patch(f"/api/workstreams/{ws['id']}", json={"owner_ids": []}).json()
    assert cleared["owners"] == []


def test_owners_are_left_alone_by_a_patch_that_does_not_mention_them(client):
    lena = _person(client, "Lena Kovacs")
    ws = _workstream(client, "S166 Response", owner_ids=[lena["id"]])

    renamed = client.patch(f"/api/workstreams/{ws['id']}", json={"name": "S166 Programme"}).json()
    assert renamed["name"] == "S166 Programme"
    assert [o["name"] for o in renamed["owners"]] == ["Lena Kovacs"]


def test_repeated_owner_id_collapses_rather_than_colliding(client):
    """The join table has a composite primary key, so a duplicate in the request
    would blow up at flush time if it were not de-duplicated first."""
    lena = _person(client, "Lena Kovacs")
    ws = _workstream(client, "S166 Response", owner_ids=[lena["id"], lena["id"]])
    assert [o["name"] for o in ws["owners"]] == ["Lena Kovacs"]


def test_unknown_owner_id_is_rejected_not_silently_dropped(client):
    resp = client.post("/api/workstreams", json={"name": "Ghost", "owner_ids": [999999]})
    assert resp.status_code == 422
    assert "999999" in resp.text


# ---------- multiple sponsors ----------


def test_topic_round_trips_several_sponsors(client):
    lena = _person(client, "Lena Kovacs")
    priya = _person(client, "Priya Shah")

    topic = client.post(
        "/api/topics", json={"title": "Sign off key messages", "sponsor_ids": [lena["id"], priya["id"]]}
    ).json()
    assert [s["name"] for s in topic["sponsors"]] == ["Lena Kovacs", "Priya Shah"]

    listed = next(t for t in client.get("/api/topics").json() if t["id"] == topic["id"])
    assert len(listed["sponsors"]) == 2

    patched = client.patch(f"/api/topics/{topic['id']}", json={"sponsor_ids": [priya["id"]]}).json()
    assert [s["name"] for s in patched["sponsors"]] == ["Priya Shah"]


def test_unknown_sponsor_id_is_rejected(client):
    resp = client.post("/api/topics", json={"title": "Ghost topic", "sponsor_ids": [999999]})
    assert resp.status_code == 422


def test_every_sponsor_sees_the_topic_in_their_one_to_one_pack(client):
    """The pack used to filter on a single sponsor_id — a co-sponsor would have
    seen nothing."""
    lena = _person(client, "Lena Kovacs")
    priya = _person(client, "Priya Shah")
    client.post("/api/topics", json={"title": "Sign off key messages", "sponsor_ids": [lena["id"], priya["id"]]})

    for person in (lena, priya):
        pack = client.get(f"/api/people/{person['id']}/pack").json()
        assert [t["title"] for t in pack["topics"]] == ["Sign off key messages"]


def test_deleting_a_person_reports_every_topic_they_co_sponsor(client):
    lena = _person(client, "Lena Kovacs")
    priya = _person(client, "Priya Shah")
    client.post("/api/topics", json={"title": "Sign off key messages", "sponsor_ids": [lena["id"], priya["id"]]})
    _workstream(client, "S166 Response", owner_ids=[lena["id"]])

    impact = client.get(f"/api/people/{lena['id']}/references").json()
    labels = {ref["label"]: ref["count"] for ref in impact["warnings"]}
    assert labels.get("topics sponsored") == 1
    assert labels.get("workstreams owned") == 1


def test_sponsor_rows_die_with_the_person(client):
    """ON DELETE CASCADE plus PRAGMA foreign_keys=ON is what keeps the join tables
    from outliving their people — nothing prunes them by hand."""
    lena = _person(client, "Lena Kovacs")
    topic = client.post("/api/topics", json={"title": "Sign off", "sponsor_ids": [lena["id"]]}).json()

    assert client.delete(f"/api/people/{lena['id']}").status_code == 204

    session = SessionLocal()
    try:
        assert session.query(Person).filter(Person.id == lena["id"]).count() == 0
        assert session.get(Topic, topic["id"]).sponsors == []
    finally:
        session.close()


def test_demo_clear_takes_the_join_rows_with_it(client):
    """The join tables have no is_demo column of their own — they rely on
    ON DELETE CASCADE from their demo parents, so a demo clear must not leave
    orphaned sponsor/owner rows behind."""
    client.post("/api/admin/seed")

    session = SessionLocal()
    try:
        from app.models.core import workstream_owner
        from app.models.meetings import topic_sponsor

        assert session.query(topic_sponsor).count() > 0
        assert session.query(workstream_owner).count() > 0
    finally:
        session.close()

    assert client.post("/api/admin/clear", json={"scope": "demo", "confirm": "CLEAR"}).status_code == 200

    session = SessionLocal()
    try:
        from app.models.core import workstream_owner
        from app.models.meetings import topic_sponsor

        assert session.query(topic_sponsor).count() == 0
        assert session.query(workstream_owner).count() == 0
    finally:
        session.close()
