from datetime import date, timedelta


def _make_person(client, name="Jamie Fox"):
    return client.post("/api/people", json={"name": name}).json()


def _make_action(client, title="Draft the pack"):
    return client.post("/api/actions", json={"title": title}).json()


def test_create_with_link_to_produces_point_and_link(client):
    person = _make_person(client)
    action = _make_action(client)

    point = client.post(
        "/api/discussion-points",
        json={
            "person_id": person["id"],
            "title": "Chase the pack",
            "link_to": {"type": "action", "id": action["id"]},
        },
    ).json()

    assert point["person_id"] == person["id"]
    assert point["status"] == "open"
    assert point["raised_on"] == date.today().isoformat()
    assert point["links"] == [{"type": "action", "id": action["id"], "title": action["title"]}]

    links = client.get(f"/api/links/for/discussion_point/{point['id']}").json()
    assert len(links) == 1
    assert links[0]["to_type"] == "action" and links[0]["to_id"] == action["id"]


def test_create_without_link_to(client):
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    ).json()
    assert point["links"] == []


def test_create_unknown_person_404(client):
    resp = client.post("/api/discussion-points", json={"person_id": 99999, "title": "x"})
    assert resp.status_code == 404


def test_create_with_bad_link_to_type_422(client):
    """discussion_point is LINKABLE, but link_to.type must still be one of the
    known linkable types -- anything else would write a Link nothing can
    resolve or ever show on the point."""
    person = _make_person(client)
    resp = client.post(
        "/api/discussion-points",
        json={"person_id": person["id"], "title": "x", "link_to": {"type": "banana", "id": 999}},
    )
    assert resp.status_code == 422


def test_link_created_to_a_point_shows_on_the_point(client):
    """discussion_point is in LINKABLE, so a link can be created the other way
    round too (e.g. from an action *to* a point via the generic LinkPanel).
    discussion_list must show it regardless of which end the point sits on."""
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    ).json()
    action = _make_action(client)

    create = client.post(
        "/api/links",
        json={
            "from_type": "action",
            "from_id": action["id"],
            "to_type": "discussion_point",
            "to_id": point["id"],
            "kind": "relates",
        },
    )
    assert create.status_code == 201

    points = client.get("/api/discussion-points", params={"person_id": person["id"]}).json()
    assert points[0]["links"] == [{"type": "action", "id": action["id"], "title": action["title"]}]


def test_link_to_discussion_point_resolves_title_and_prunes_on_demo_clear(client):
    """Part 0 fix: discussion_point registered in TITLE_RESOLVERS. Without it,
    a link naming a discussion point would render as the literal
    "discussion_point #N" and survive a demo clear that deletes the point it
    points at."""
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    ).json()
    action = _make_action(client)

    link = client.post(
        "/api/links",
        json={
            "from_type": "action",
            "from_id": action["id"],
            "to_type": "discussion_point",
            "to_id": point["id"],
            "kind": "relates",
        },
    ).json()
    assert link["to_title"] == "Ask about headcount"

    from app.db import SessionLocal
    from app.models import DiscussionPoint, Link

    session = SessionLocal()
    try:
        row = session.get(DiscussionPoint, point["id"])
        row.is_demo = True
        session.commit()
    finally:
        session.close()

    result = client.post("/api/admin/clear", json={"scope": "demo", "confirm": "CLEAR"}).json()
    assert result["cleared"] == "demo"

    session = SessionLocal()
    try:
        assert session.get(DiscussionPoint, point["id"]) is None
        assert session.get(Link, link["id"]) is None
    finally:
        session.close()


def test_discussed_stamps_and_increments_once_per_day(client):
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Standing item"}
    ).json()
    assert point["last_discussed_on"] is None
    assert point["times_discussed"] == 0

    first = client.post(f"/api/discussion-points/{point['id']}/discussed").json()
    assert first["last_discussed_on"] == date.today().isoformat()
    assert first["times_discussed"] == 1

    # a second call the same day must not inflate the count
    second = client.post(f"/api/discussion-points/{point['id']}/discussed").json()
    assert second["times_discussed"] == 1
    assert second["last_discussed_on"] == date.today().isoformat()


def test_closing_stamps_closed_on_and_drops_from_default_list(client):
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "One-off ask"}
    ).json()

    closed = client.patch(f"/api/discussion-points/{point['id']}", json={"status": "closed"}).json()
    assert closed["status"] == "closed"
    assert closed["closed_on"] == date.today().isoformat()

    open_list = client.get(
        "/api/discussion-points", params={"person_id": person["id"]}
    ).json()
    assert open_list == []

    with_closed = client.get(
        "/api/discussion-points", params={"person_id": person["id"], "include_closed": True}
    ).json()
    assert [p["id"] for p in with_closed] == [point["id"]]


def test_ordering_never_discussed_first_then_stalest(client):
    person = _make_person(client)

    # discussed recently -- should sort last among the discussed ones
    recent = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Discussed recently"}
    ).json()
    client.post(f"/api/discussion-points/{recent['id']}/discussed")

    # the API can only stamp last_discussed_on as "today", so a second
    # discussed point can't be made staler than "recent" through this door --
    # the actual date comparison is covered directly against the service in
    # test_ordering_stalest_before_least_stale below. Here we only need
    # never-discussed to rank ahead of anything that has been discussed.
    stale = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Discussed a while ago"}
    ).json()
    client.post(f"/api/discussion-points/{stale['id']}/discussed")

    never = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Never discussed"}
    ).json()

    ordered = client.get("/api/discussion-points", params={"person_id": person["id"]}).json()
    ids = [p["id"] for p in ordered]
    assert ids.index(never["id"]) < ids.index(recent["id"])
    assert ids.index(never["id"]) < ids.index(stale["id"])


def test_ordering_stalest_before_least_stale(db):
    """Exercise the actual date comparison directly against the service, since
    the API has no way to backdate last_discussed_on."""
    from app.models import DiscussionPoint, Person
    from app.services.discussion import discussion_list

    person = Person(name="Ordering Test")
    db.add(person)
    db.flush()

    today = date.today()
    fresher = DiscussionPoint(
        person_id=person.id, title="Fresher", raised_on=today,
        last_discussed_on=today - timedelta(days=1),
    )
    staler = DiscussionPoint(
        person_id=person.id, title="Staler", raised_on=today,
        last_discussed_on=today - timedelta(days=10),
    )
    never = DiscussionPoint(person_id=person.id, title="Never", raised_on=today)
    db.add_all([fresher, staler, never])
    db.commit()

    rows = discussion_list(db, person.id)
    ids = [r["id"] for r in rows]
    assert ids == [never.id, staler.id, fresher.id]


def test_pinning_second_person_unpins_first(client):
    alice = _make_person(client, "Alice")
    bob = _make_person(client, "Bob")

    client.patch(f"/api/people/{alice['id']}", json={"pin_discussion": True})
    alice_after = client.get("/api/people").json()
    assert next(p for p in alice_after if p["id"] == alice["id"])["pin_discussion"] is True

    client.patch(f"/api/people/{bob['id']}", json={"pin_discussion": True})
    people_after = {p["id"]: p for p in client.get("/api/people").json()}
    assert people_after[bob["id"]]["pin_discussion"] is True
    assert people_after[alice["id"]]["pin_discussion"] is False


def test_dashboard_summary_reflects_pinned_person(client):
    person = _make_person(client)
    client.patch(f"/api/people/{person['id']}", json={"pin_discussion": True})
    client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    )

    summary = client.get("/api/dashboard/summary").json()
    assert summary["discussion"]["person"]["id"] == person["id"]
    assert len(summary["discussion"]["points"]) == 1

    # unpin -> nobody pinned -> null, not an error
    client.patch(f"/api/people/{person['id']}", json={"pin_discussion": False})
    summary_after = client.get("/api/dashboard/summary").json()
    assert summary_after["discussion"] is None


def test_pack_endpoint_includes_discussion_points(client):
    person = _make_person(client)
    client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    )
    pack = client.get(f"/api/people/{person['id']}/pack").json()
    assert len(pack["discussion_points"]) == 1
    assert pack["discussion_points"][0]["title"] == "Ask about headcount"


def test_person_delete_preflight_warns_and_cascades(client):
    person = _make_person(client)
    point = client.post(
        "/api/discussion-points", json={"person_id": person["id"], "title": "Ask about headcount"}
    ).json()

    refs = client.get(f"/api/people/{person['id']}/references").json()
    labels = {w["label"]: w for w in refs["warnings"]}
    assert labels["discussion points"]["count"] == 1

    assert client.delete(f"/api/people/{person['id']}").status_code == 204
    assert client.get("/api/discussion-points", params={"person_id": person["id"]}).status_code == 404

    # the row is actually gone at the DB level, not just unreachable via the
    # person-scoped endpoint
    from app.db import SessionLocal
    from app.models import DiscussionPoint

    session = SessionLocal()
    try:
        assert session.get(DiscussionPoint, point["id"]) is None
    finally:
        session.close()


def test_demo_clear_removes_discussion_points(client):
    seeded = client.post("/api/admin/seed").json()
    assert seeded["discussion_points"] == 2

    before = client.get("/api/admin/stats").json()
    assert before["discussion_point"] == 2

    result = client.post("/api/admin/clear", json={"scope": "demo", "confirm": "CLEAR"}).json()
    assert result["cleared"] == "demo"

    after = client.get("/api/admin/stats").json()
    assert after["discussion_point"] == 0
