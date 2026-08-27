from datetime import datetime, timedelta

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models import AgendaItem, DiaryEvent, Forum, Meeting, Person, Topic, Workstream

# ---------- seed helpers (mirrors the direct-session style used in test_diary_link.py) ----------


def add_forum(session, name="Test Forum", capacity_minutes=60):
    forum = Forum(name=name, capacity_minutes=capacity_minutes)
    session.add(forum)
    session.flush()
    return forum


def add_meeting(session, forum_id, scheduled_at, **kwargs):
    meeting = Meeting(forum_id=forum_id, scheduled_at=scheduled_at, **kwargs)
    session.add(meeting)
    session.flush()
    return meeting


def add_workstream(session, name, category="initiative"):
    workstream = Workstream(name=name, category=category)
    session.add(workstream)
    session.flush()
    return workstream


def add_topic(session, title, **kwargs):
    topic = Topic(title=title, **kwargs)
    session.add(topic)
    session.flush()
    return topic


def add_agenda_item(session, meeting_id, topic_id, sequence, allocated_minutes=15, **kwargs):
    item = AgendaItem(
        meeting_id=meeting_id,
        topic_id=topic_id,
        sequence=sequence,
        allocated_minutes=allocated_minutes,
        **kwargs,
    )
    session.add(item)
    session.flush()
    return item


URL = "/api/forums/{forum_id}/rolling-agenda"


# ---------- headline case ----------


def test_recurring_topic_yields_one_row_with_multiple_cells(client):
    session = SessionLocal()
    try:
        forum = add_forum(session, name="AET Weekly")
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meetings = [add_meeting(session, forum_id, base + timedelta(days=7 * i)) for i in range(3)]
        topic = add_topic(session, "Standing MI Review", recurring=True, duration_minutes=20)
        for m in meetings:
            add_agenda_item(session, m.id, topic.id, sequence=1, allocated_minutes=20)
        session.commit()
        meeting_ids = [m.id for m in meetings]
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id), params={"limit": 8}).json()
    assert [m["id"] for m in body["meetings"]] == meeting_ids

    assert len(body["bands"]) == 1
    band = body["bands"][0]
    assert len(band["rows"]) == 1
    row = band["rows"][0]
    assert row["topic"]["title"] == "Standing MI Review"
    assert row["topic"]["recurring"] is True
    assert len(row["cells"]) == 3
    assert all(cell is not None for cell in row["cells"])
    assert [c["meeting_id"] for c in row["cells"]] == meeting_ids


def test_topic_on_first_and_third_meeting_leaves_middle_cell_null(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meetings = [add_meeting(session, forum_id, base + timedelta(days=7 * i)) for i in range(3)]
        topic = add_topic(session, "Occasional Item")
        add_agenda_item(session, meetings[0].id, topic.id, sequence=1)
        add_agenda_item(session, meetings[2].id, topic.id, sequence=1)
        session.commit()
        m_ids = [m.id for m in meetings]
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    row = body["bands"][0]["rows"][0]
    cells = row["cells"]
    assert cells[1] is None
    assert cells[0] is not None and cells[0]["meeting_id"] == m_ids[0]
    assert cells[2] is not None and cells[2]["meeting_id"] == m_ids[2]


def test_every_row_cells_length_matches_meetings_length(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meetings = [add_meeting(session, forum_id, base + timedelta(days=i)) for i in range(5)]
        ws_a = add_workstream(session, "Alpha Programme")
        topics = [
            add_topic(session, "Standing item", recurring=True, workstream_id=ws_a.id),
            add_topic(session, "One-off A"),
            add_topic(session, "One-off B", workstream_id=ws_a.id),
        ]
        # standing item on every meeting; one-offs scattered
        for m in meetings:
            add_agenda_item(session, m.id, topics[0].id, sequence=1)
        add_agenda_item(session, meetings[1].id, topics[1].id, sequence=2)
        add_agenda_item(session, meetings[3].id, topics[2].id, sequence=2)
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    n = len(body["meetings"])
    assert n == 5
    for band in body["bands"]:
        for row in band["rows"]:
            assert len(row["cells"]) == n


# ---------- band grouping & ordering ----------


def test_unassigned_band_is_always_last_even_when_it_sorts_first_alphabetically(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meeting = add_meeting(session, forum_id, base)
        # names chosen to sort AFTER "Unassigned" alphabetically, to prove the
        # ordering rule isn't alphabetical luck
        ws_zeta = add_workstream(session, "Zeta Programme", category="initiative")
        ws_zulu = add_workstream(session, "Zulu Programme", category="initiative")
        t_unassigned = add_topic(session, "No workstream topic")
        t_zeta = add_topic(session, "Zeta topic", workstream_id=ws_zeta.id)
        t_zulu = add_topic(session, "Zulu topic", workstream_id=ws_zulu.id)
        for i, t in enumerate([t_unassigned, t_zeta, t_zulu]):
            add_agenda_item(session, meeting.id, t.id, sequence=i + 1)
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    labels = [b["label"] for b in body["bands"]]
    assert labels == ["Zeta Programme", "Zulu Programme", "Unassigned"]
    assert body["bands"][-1]["workstream"] is None
    assert body["bands"][-1]["category"] is None


def test_bands_ordered_by_category_then_label(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meeting = add_meeting(session, forum_id, base)
        ws_gov_bravo = add_workstream(session, "Bravo Board Pack", category="governance")
        ws_audit_alpha = add_workstream(session, "Alpha Audit", category="audit")
        ws_audit_zulu = add_workstream(session, "Zulu Audit", category="audit")
        topics = [
            add_topic(session, "T-gov", workstream_id=ws_gov_bravo.id),
            add_topic(session, "T-audit-a", workstream_id=ws_audit_alpha.id),
            add_topic(session, "T-audit-z", workstream_id=ws_audit_zulu.id),
        ]
        for i, t in enumerate(topics):
            add_agenda_item(session, meeting.id, t.id, sequence=i + 1)
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    pairs = [(b["category"], b["label"]) for b in body["bands"]]
    assert pairs == [
        ("audit", "Alpha Audit"),
        ("audit", "Zulu Audit"),
        ("governance", "Bravo Board Pack"),
    ]


def test_rows_within_band_ordered_by_earliest_cell_then_title(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meetings = [add_meeting(session, forum_id, base + timedelta(days=i)) for i in range(3)]
        ws = add_workstream(session, "Shared Workstream")
        # "Z topic" appears earliest (meeting 0); "A topic" appears later (meeting 1)
        t_z = add_topic(session, "Z topic", workstream_id=ws.id)
        t_a = add_topic(session, "A topic", workstream_id=ws.id)
        t_b = add_topic(session, "B topic", workstream_id=ws.id)  # ties with t_a on meeting 1
        add_agenda_item(session, meetings[0].id, t_z.id, sequence=1)
        add_agenda_item(session, meetings[1].id, t_a.id, sequence=1)
        add_agenda_item(session, meetings[1].id, t_b.id, sequence=2)
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    titles = [row["topic"]["title"] for row in body["bands"][0]["rows"]]
    # Z topic first (earliest cell at index 0), then A/B tie at index 1 broken by title
    assert titles == ["Z topic", "A topic", "B topic"]


# ---------- minutes & capacity ----------


def test_allocated_and_capacity_minutes(client):
    session = SessionLocal()
    try:
        forum = add_forum(session, capacity_minutes=90)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        meeting = add_meeting(session, forum_id, base)
        t1 = add_topic(session, "Item one")
        t2 = add_topic(session, "Item two")
        add_agenda_item(session, meeting.id, t1.id, sequence=1, allocated_minutes=15)
        add_agenda_item(session, meeting.id, t2.id, sequence=2, allocated_minutes=20)
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    m = body["meetings"][0]
    assert m["allocated_minutes"] == 35
    assert m["capacity_minutes"] == 90
    assert m["item_count"] == 2


# ---------- location ----------


def test_location_from_linked_diary_event_and_none_when_unlinked(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        session.add(
            DiaryEvent(
                id="EVT-ROLL-1",
                subject="AET Weekly",
                location="Boardroom A",
                status="active",
            )
        )
        session.flush()
        linked = add_meeting(session, forum_id, base, diary_event_id="EVT-ROLL-1")
        unlinked = add_meeting(session, forum_id, base + timedelta(days=7))
        session.commit()
        linked_id, unlinked_id = linked.id, unlinked.id
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    by_id = {m["id"]: m for m in body["meetings"]}
    assert by_id[linked_id]["location"] == "Boardroom A"
    assert by_id[unlinked_id]["location"] is None


# ---------- include_past / -12h boundary ----------


def test_include_past_false_excludes_old_meeting_but_keeps_the_12h_boundary(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        now = datetime.now()
        old = add_meeting(session, forum_id, now - timedelta(days=3))
        boundary = add_meeting(session, forum_id, now - timedelta(hours=2))
        session.commit()
        old_id, boundary_id = old.id, boundary.id
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    ids = [m["id"] for m in body["meetings"]]
    assert boundary_id in ids
    assert old_id not in ids

    body_all = client.get(URL.format(forum_id=forum_id), params={"include_past": "true"}).json()
    ids_all = [m["id"] for m in body_all["meetings"]]
    assert old_id in ids_all
    assert boundary_id in ids_all


# ---------- limit ----------


def test_limit_caps_meeting_count(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        for i in range(5):
            add_meeting(session, forum_id, base + timedelta(days=i))
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id), params={"limit": 3}).json()
    assert len(body["meetings"]) == 3


def test_limit_over_24_is_rejected(client):
    # Previously silently clamped via `min(limit, 24)`; now enforced by
    # `Query(..., le=24)` so the bound is documented in OpenAPI and can't be
    # bypassed (see the negative-limit case below).
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        ids = []
        for i in range(30):
            m = add_meeting(session, forum_id, base + timedelta(days=i))
            ids.append(m.id)
        session.commit()
    finally:
        session.close()

    resp = client.get(URL.format(forum_id=forum_id), params={"limit": 100})
    assert resp.status_code == 422


def test_limit_negative_is_rejected(client):
    # SQLite treats `LIMIT -1` as unlimited, so a naive `min(limit, 24)` clamp
    # doesn't hold for negative input — the cap must be enforced by request
    # validation instead, not by clamping in Python.
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        session.commit()
    finally:
        session.close()

    resp = client.get(URL.format(forum_id=forum_id), params={"limit": -1})
    assert resp.status_code == 422


# ---------- empty cases ----------


def test_forum_with_meetings_but_no_agenda_items_has_no_bands(client):
    session = SessionLocal()
    try:
        forum = add_forum(session)
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        add_meeting(session, forum_id, base)
        add_meeting(session, forum_id, base + timedelta(days=7))
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    assert len(body["meetings"]) == 2
    assert body["bands"] == []


def test_forum_with_no_meetings(client):
    session = SessionLocal()
    try:
        forum = add_forum(session, name="Empty Forum")
        forum_id = forum.id
        session.commit()
    finally:
        session.close()

    body = client.get(URL.format(forum_id=forum_id)).json()
    assert body["meetings"] == []
    assert body["bands"] == []
    assert body["forum"]["name"] == "Empty Forum"


def test_unknown_forum_404(client):
    resp = client.get(URL.format(forum_id=999999))
    assert resp.status_code == 404


# ---------- query count sanity ----------


def test_query_count_is_small_and_constant(client):
    session = SessionLocal()
    try:
        forum = add_forum(session, name="Busy Forum")
        forum_id = forum.id
        base = datetime.now() + timedelta(days=1)
        sponsor = Person(name="Priya Shah")
        session.add(sponsor)
        session.flush()
        workstreams = [add_workstream(session, f"WS {i}") for i in range(3)]
        meetings = [add_meeting(session, forum_id, base + timedelta(days=7 * i)) for i in range(8)]
        topics = [
            add_topic(
                session,
                f"Topic {i}",
                workstream_id=workstreams[i % 3].id,
                sponsors=[sponsor],
            )
            for i in range(6)
        ]
        seq = 1
        for m in meetings:
            for t in topics:
                add_agenda_item(session, m.id, t.id, sequence=seq)
                seq += 1
        session.commit()
    finally:
        session.close()

    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        resp = client.get(URL.format(forum_id=forum_id), params={"limit": 8})
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["meetings"]) == 8
    assert sum(len(b["rows"]) for b in body["bands"]) == 6  # 6 distinct topics, not 48 rows

    # 8 meetings x 6 items = 48 agenda items; a broken N+1 loader would blow this
    # number up proportionally. The real loader chain is: forum, meetings,
    # agenda_items, topic, sponsors, workstream, (no diary lookup here) -> ~6.
    # sponsors is many-to-many now, but selectinload still batches it into one
    # SELECT through the join table, so the budget is unchanged.
    assert len(statements) <= 10, f"expected a small constant number of queries, got: {statements}"
