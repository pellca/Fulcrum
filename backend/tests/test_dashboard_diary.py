from datetime import date, datetime, timedelta

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models import AgendaItem, DiaryEvent, Forum, Meeting, Topic

TODAY = date.today()
TODAY_STR = TODAY.isoformat()


def _event(id, **kwargs):
    defaults = dict(
        subject="Event",
        start_date=TODAY_STR,
        start_time="09:00",
        end_time="09:30",
        is_all_day=False,
        status="active",
        location=None,
        organizer=None,
    )
    defaults.update(kwargs)
    return DiaryEvent(id=id, **defaults)


def test_only_todays_events_returned(client):
    session = SessionLocal()
    try:
        session.add_all(
            [
                _event("today", subject="Today's event"),
                _event("yesterday", subject="Yesterday", start_date=(TODAY - timedelta(days=1)).isoformat()),
                _event("tomorrow", subject="Tomorrow", start_date=(TODAY + timedelta(days=1)).isoformat()),
            ]
        )
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    assert [d["id"] for d in diary] == ["today"]
    assert diary[0]["subject"] == "Today's event"


def test_cancelled_events_excluded(client):
    session = SessionLocal()
    try:
        session.add_all(
            [
                _event("active", subject="Still on"),
                _event("cancelled", subject="Called off", status="cancelled"),
            ]
        )
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    assert [d["id"] for d in diary] == ["active"]


def test_all_day_sorts_first(client):
    session = SessionLocal()
    try:
        session.add_all(
            [
                _event("early-timed", subject="Early timed", start_time="08:00"),
                _event("all-day", subject="All day thing", is_all_day=True, start_time=None),
                _event("late-timed", subject="Late timed", start_time="17:00"),
            ]
        )
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    assert [d["id"] for d in diary] == ["all-day", "early-timed", "late-timed"]


def test_unlinked_event_returns_meeting_null(client):
    session = SessionLocal()
    try:
        session.add(_event("solo", subject="No Fulcrum meeting"))
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    assert diary[0]["meeting"] is None


def test_linked_meeting_brings_agenda_count_and_capacity(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", colour="#123456", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(_event("linked", subject="AET Weekly"))
        session.flush()
        meeting = Meeting(
            forum_id=forum.id,
            scheduled_at=datetime.combine(TODAY, datetime.min.time()),
            diary_event_id="linked",
            status="agenda_set",
        )
        session.add(meeting)
        session.flush()
        topic = Topic(title="Budget review", duration_minutes=15)
        session.add(topic)
        session.flush()
        session.add(AgendaItem(meeting_id=meeting.id, topic_id=topic.id, sequence=1, allocated_minutes=20))
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    entry = diary[0]
    assert entry["meeting"] is not None
    assert entry["meeting"]["forum"] == "AET Weekly"
    assert entry["meeting"]["colour"] == "#123456"
    assert entry["meeting"]["status"] == "agenda_set"
    assert entry["meeting"]["agenda_count"] == 1
    assert entry["meeting"]["allocated_minutes"] == 20
    assert entry["meeting"]["capacity_minutes"] == 60


def test_query_count_is_small_and_constant_with_several_linked_events(client):
    session = SessionLocal()
    try:
        # distinct forums per meeting so a broken (non-eager) forum lookup
        # would show up as one extra statement per meeting, not be masked by
        # the identity map serving repeat lookups of the same forum row
        forums = [Forum(name=f"Forum {i}", capacity_minutes=60) for i in range(6)]
        session.add_all(forums)
        session.flush()
        for i in range(6):
            event_id = f"linked-{i}"
            session.add(_event(event_id, subject=f"Meeting {i}", start_time=f"{9 + i:02d}:00"))
            session.flush()
            meeting = Meeting(
                forum_id=forums[i].id,
                scheduled_at=datetime.combine(TODAY, datetime.min.time()),
                diary_event_id=event_id,
            )
            session.add(meeting)
            session.flush()
            topic = Topic(title=f"Topic {i}", duration_minutes=10)
            session.add(topic)
            session.flush()
            session.add(AgendaItem(meeting_id=meeting.id, topic_id=topic.id, sequence=1, allocated_minutes=10))
        # a handful of unlinked events too, so the batch query still has to
        # skip them without costing an extra statement each
        for i in range(4):
            session.add(_event(f"unlinked-{i}", subject=f"Solo {i}", start_time=f"{15 + i:02d}:00"))
        session.commit()
    finally:
        session.close()

    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        resp = client.get("/api/dashboard/summary")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp.status_code == 200
    diary = resp.json()["diary"]
    assert len(diary) == 10
    assert sum(1 for d in diary if d["meeting"] is not None) == 6

    # the diary block itself should cost a small constant number of
    # statements regardless of how many linked meetings/agenda items exist:
    # the events query, the batched Meeting query (diary_event_id IN (...))
    # with agenda_items + forum eager-loaded. A broken per-event loader would
    # scale with the 6 linked events, not stay flat.
    # the whole /dashboard/summary payload costs ~13 statements here; a
    # regression back to a per-event Meeting lookup or a lazy (non-eager)
    # Meeting.forum access would add roughly one statement per linked event
    # (6), so this bound has room for unrelated summary blocks to grow a
    # little without room for that regression to hide in.
    assert len(statements) <= 16, f"expected a small constant number of queries, got: {statements}"


# ---------- multi-day events and the imported flag ----------


def test_event_spanning_today_stays_on_the_brief(client):
    """A three-day offsite has to show on all three days. Matching on
    start_date alone dropped it after day one, which is exactly backwards for
    the entries a principal most needs to see."""
    session = SessionLocal()
    try:
        session.add_all(
            [
                _event(
                    "offsite",
                    subject="Audit Committee offsite",
                    start_date=(TODAY - timedelta(days=1)).isoformat(),
                    end_date=(TODAY + timedelta(days=1)).isoformat(),
                    is_all_day=True,
                    start_time=None,
                    end_time=None,
                ),
                _event(
                    "finished",
                    subject="Ended yesterday",
                    start_date=(TODAY - timedelta(days=3)).isoformat(),
                    end_date=(TODAY - timedelta(days=1)).isoformat(),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    diary = client.get("/api/dashboard/summary").json()["diary"]
    assert [d["id"] for d in diary] == ["offsite"]
    assert (diary[0]["span_day"], diary[0]["span_days"]) == (2, 3)


def test_single_day_event_reports_a_span_of_one(client):
    """(1, 1) is the signal the UI uses to say nothing about spans at all."""
    session = SessionLocal()
    try:
        session.add(_event("single", subject="Catch-up"))
        session.commit()
    finally:
        session.close()

    entry = client.get("/api/dashboard/summary").json()["diary"][0]
    assert (entry["span_day"], entry["span_days"]) == (1, 1)


def test_null_end_date_is_treated_as_a_single_day(client):
    """The extractor doesn't always populate end_date; a null must not make an
    old event immortal on the dashboard."""
    session = SessionLocal()
    try:
        session.add_all(
            [
                _event("old", subject="Long gone", start_date=(TODAY - timedelta(days=30)).isoformat()),
                _event("now", subject="Today"),
            ]
        )
        session.commit()
    finally:
        session.close()

    assert [d["id"] for d in client.get("/api/dashboard/summary").json()["diary"]] == ["now"]


def test_diary_imported_flag_distinguishes_empty_day_from_no_import(client):
    """The card shows different empty states for the two, and it must not cost
    a second round trip to /admin/stats to tell them apart."""
    assert client.get("/api/dashboard/summary").json()["diary_imported"] is False

    session = SessionLocal()
    try:
        session.add(_event("tomorrow-only", start_date=(TODAY + timedelta(days=1)).isoformat()))
        session.commit()
    finally:
        session.close()

    summary = client.get("/api/dashboard/summary").json()
    assert summary["diary"] == []
    assert summary["diary_imported"] is True
