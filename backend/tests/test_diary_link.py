import time
from datetime import datetime

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models import AgendaItem, Decision, DiaryEvent, Forum, Meeting, Topic
from app.services.diary_match import score_pair

# ---------- score_pair: pure function, no DB ----------


def test_score_pair_exact_time_and_identical_subject_is_high():
    meeting_dt = datetime(2026, 8, 3, 10, 0)
    event_dt = datetime(2026, 8, 3, 10, 0)
    result = score_pair("AET Weekly", "AET Weekly", meeting_dt, event_dt, within_minutes=120)
    assert result is not None
    score, reasons = result
    assert score >= 70
    assert any("10:00" in r for r in reasons)


def test_score_pair_acronym_with_time_gap_is_likely():
    meeting_dt = datetime(2026, 8, 3, 9, 0)
    event_dt = datetime(2026, 8, 3, 10, 30)  # 90 minutes apart
    result = score_pair("Audit Executive Team", "AET Weekly", meeting_dt, event_dt, within_minutes=120)
    assert result is not None
    score, reasons = result
    assert 45 <= score < 70
    assert any("acronym" in r.lower() for r in reasons)


def test_score_pair_same_subject_different_day_is_none():
    meeting_dt = datetime(2026, 8, 3, 10, 0)
    event_dt = datetime(2026, 8, 4, 10, 0)
    assert score_pair("AET Weekly", "AET Weekly", meeting_dt, event_dt, within_minutes=120) is None


def test_score_pair_same_time_unrelated_subject_is_none():
    meeting_dt = datetime(2026, 8, 3, 10, 0)
    event_dt = datetime(2026, 8, 3, 10, 0)
    assert score_pair("AET Weekly", "Random unrelated title", meeting_dt, event_dt, within_minutes=120) is None


def test_score_pair_stopword_only_overlap_is_none():
    meeting_dt = datetime(2026, 8, 3, 10, 0)
    event_dt = datetime(2026, 8, 3, 10, 0)
    assert score_pair("Weekly Meeting", "Monthly Meeting", meeting_dt, event_dt, within_minutes=120) is None


def test_score_pair_committee_only_overlap_is_none():
    # "Group Risk Committee" vs "Group Audit Committee" — two different bank
    # committees that happen to share the generic word "committee". Without
    # "committee" in STOPWORDS this used to jaccard-match at 0.5 and score 70.
    meeting_dt = datetime(2026, 8, 3, 14, 0)
    event_dt = datetime(2026, 8, 3, 14, 0)
    assert (
        score_pair("Group Risk Committee", "Group Audit Committee", meeting_dt, event_dt, within_minutes=120)
        is None
    )


# ---------- suggest_links via GET /diary/link-suggestions ----------


def test_suggest_links_one_to_one_when_two_meetings_match_one_event(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 10, 0)))
        session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 10, 5)))
        session.add(
            DiaryEvent(
                id="EVT1", subject="AET Weekly", start_date="2026-08-03", start_time="10:00", status="active"
            )
        )
        session.commit()
    finally:
        session.close()

    suggestions = client.get("/api/diary/link-suggestions").json()
    assert len(suggestions) == 1
    assert suggestions[0]["diary_event_id"] == "EVT1"


def test_suggest_links_excludes_linked_events_and_cancelled_meetings(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(
            DiaryEvent(
                id="EVT-LINKED",
                subject="AET Weekly",
                start_date="2026-08-03",
                start_time="10:00",
                status="active",
            )
        )
        session.flush()
        # already linked -> its event must not be offered again
        session.add(
            Meeting(
                forum_id=forum.id,
                scheduled_at=datetime(2026, 8, 3, 10, 0),
                diary_event_id="EVT-LINKED",
            )
        )
        # cancelled meeting -> must not consume a candidate event
        session.add(
            Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 10, 0), status="cancelled")
        )
        session.add(
            DiaryEvent(
                id="EVT-FREE", subject="AET Weekly", start_date="2026-08-03", start_time="10:00", status="active"
            )
        )
        session.commit()
    finally:
        session.close()

    suggestions = client.get("/api/diary/link-suggestions").json()
    assert suggestions == []


def test_suggest_links_only_scores_same_day_candidates_and_stays_fast(client):
    """Guards the O(meetings x events) -> date-bucketed rewrite: hundreds of
    decoy events on other dates must neither corrupt the result nor make the
    call slow, since score_pair's first hard gate is same-calendar-day."""
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 10, 0)))
        session.add(
            DiaryEvent(
                id="MATCH", subject="AET Weekly", start_date="2026-08-03", start_time="10:00", status="active"
            )
        )
        # decoys spread across many other dates (never August, so they can't
        # collide with the real meeting's date), some sharing the subject
        # text on purpose to prove the date gate — not just the subject
        # gate — is what's keeping them out.
        for i in range(300):
            month = 1 + (i % 6)
            day = 1 + (i % 27)
            session.add(
                DiaryEvent(
                    id=f"DECOY-{i}",
                    subject="AET Weekly",
                    start_date=f"2026-{month:02d}-{day:02d}",
                    start_time="10:00",
                    status="active",
                )
            )
        session.commit()
    finally:
        session.close()

    start = time.monotonic()
    suggestions = client.get("/api/diary/link-suggestions").json()
    elapsed = time.monotonic() - start

    assert len(suggestions) == 1
    assert suggestions[0]["diary_event_id"] == "MATCH"
    assert elapsed < 2.0, f"suggest_links took {elapsed:.2f}s for 300 decoy events"


def test_suggest_links_query_count_does_not_scale_with_meeting_count(client):
    """Meeting.forum used to be an N+1 (one SELECT per meeting); it must now
    be loaded in one batch regardless of how many meetings are in play."""
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        for i in range(20):
            session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 1 + (i % 27), 10, 0)))
        session.commit()
    finally:
        session.close()

    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        resp = client.get("/api/diary/link-suggestions")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp.status_code == 200
    # meetings (+selectinload forum), linked-meetings, events -> small constant
    assert len(statements) <= 6, f"expected a small constant number of queries, got: {statements}"


def test_group_risk_vs_group_audit_committee_never_comes_back_as_a_suggestion(client):
    """Pins the real false positive: two different bank committees, same
    slot, that used to score exactly 70.0 and show a green 'high' badge."""
    session = SessionLocal()
    try:
        forum = Forum(name="Group Risk Committee", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 14, 0)))
        session.add(
            DiaryEvent(
                id="EVT-GRC",
                subject="Group Audit Committee",
                start_date="2026-08-03",
                start_time="14:00",
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    suggestions = client.get("/api/diary/link-suggestions").json()
    assert all(s["diary_event_id"] != "EVT-GRC" for s in suggestions)


def test_token_overlap_alone_is_never_high_confidence_even_above_70(client):
    """confidence == 'high' is reserved for a structural match (Title match or
    an acronym hit) — a bare token-overlap ("Similar title") must stay
    'likely' no matter how high the numeric score climbs."""
    session = SessionLocal()
    try:
        forum = Forum(name="Alpha Beta Gamma", capacity_minutes=60)
        session.add(forum)
        session.flush()
        session.add(Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 8, 3, 14, 0)))
        session.add(
            DiaryEvent(
                id="EVT-ABG", subject="Gamma Alpha", start_date="2026-08-03", start_time="14:00", status="active"
            )
        )
        session.commit()
    finally:
        session.close()

    suggestions = client.get("/api/diary/link-suggestions").json()
    match = next(s for s in suggestions if s["diary_event_id"] == "EVT-ABG")
    assert match["score"] >= 70
    assert match["confidence"] == "likely"
    assert not any(r == "Title match" or r.startswith("Acronym match") for r in match["reasons"])


# ---------- POST /diary/create-meeting ----------


def test_create_meeting_existing_forum(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        forum_id = forum.id
        session.add(
            DiaryEvent(
                id="EVT1",
                subject="AET Weekly",
                start_date="2026-08-03",
                start_time="10:00",
                end_date="2026-08-03",
                end_time="11:00",
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    resp = client.post("/api/diary/create-meeting", json={"diary_event_id": "EVT1", "forum_id": forum_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scheduled_at"] == "2026-08-03T10:00:00"
    assert body["diary_event_id"] == "EVT1"
    assert body["needs_review"] is False

    # second call for the same event -> 409
    resp2 = client.post("/api/diary/create-meeting", json={"diary_event_id": "EVT1", "forum_id": forum_id})
    assert resp2.status_code == 409


def test_create_meeting_new_forum_capacity_from_event_duration(client):
    session = SessionLocal()
    try:
        session.add(
            DiaryEvent(
                id="EVT2",
                subject="Credit Risk Deep Dive",
                start_date="2026-08-04",
                start_time="09:00",
                end_date="2026-08-04",
                end_time="10:30",
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    resp = client.post(
        "/api/diary/create-meeting",
        json={"diary_event_id": "EVT2", "new_forum_name": "Credit Risk Deep Dive"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["forum"]["name"] == "Credit Risk Deep Dive"
    assert body["forum"]["capacity_minutes"] == 90  # 09:00 -> 10:30


def test_create_meeting_requires_exactly_one_forum_arg(client):
    session = SessionLocal()
    try:
        session.add(
            DiaryEvent(id="EVT3", subject="X", start_date="2026-08-05", start_time="09:00", status="active")
        )
        forum = Forum(name="Somewhere", capacity_minutes=60)
        session.add(forum)
        session.commit()
        forum_id = forum.id
    finally:
        session.close()

    # neither
    assert client.post("/api/diary/create-meeting", json={"diary_event_id": "EVT3"}).status_code == 422
    # both
    assert (
        client.post(
            "/api/diary/create-meeting",
            json={"diary_event_id": "EVT3", "forum_id": forum_id, "new_forum_name": "Dup"},
        ).status_code
        == 422
    )


def test_create_meeting_negative_capacity_is_422(client):
    session = SessionLocal()
    try:
        session.add(
            DiaryEvent(id="EVT-NEG-CAP", subject="X", start_date="2026-08-06", start_time="09:00", status="active")
        )
        session.commit()
    finally:
        session.close()

    resp = client.post(
        "/api/diary/create-meeting",
        json={
            "diary_event_id": "EVT-NEG-CAP",
            "new_forum_name": "Bad Capacity",
            "new_forum_capacity_minutes": -500,
        },
    )
    assert resp.status_code == 422

    session = SessionLocal()
    try:
        assert session.query(Forum).filter(Forum.name == "Bad Capacity").first() is None
    finally:
        session.close()


def test_create_meeting_unknown_event_404(client):
    resp = client.post(
        "/api/diary/create-meeting", json={"diary_event_id": "NOPE", "new_forum_name": "X"}
    )
    assert resp.status_code == 404


# ---------- check_references (delete hygiene) ----------


def test_check_references_meeting_and_diary_event(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        event = DiaryEvent(
            id="AAMkAG...xyz|2026-07-06T13:00:00Z",
            subject="AET Weekly",
            start_date="2026-07-06",
            start_time="13:00",
            status="active",
        )
        session.add(event)
        session.flush()
        meeting = Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 7, 6, 13, 0), diary_event_id=event.id)
        session.add(meeting)
        session.flush()
        topic = Topic(title="Budget update")
        session.add(topic)
        session.flush()
        session.add(AgendaItem(meeting_id=meeting.id, topic_id=topic.id, sequence=0, allocated_minutes=15))
        session.add(Decision(meeting_id=meeting.id, title="Approved budget"))
        session.commit()
        meeting_id = meeting.id
        event_id = event.id
    finally:
        session.close()

    meeting_check = client.post("/api/bulk/check", json={"type": "meeting", "ids": [meeting_id]}).json()
    labels = {w["label"] for w in meeting_check["warnings"]}
    assert "agenda items that will be removed" in labels
    assert "decisions that will lose their meeting" in labels

    diary_check = client.post("/api/bulk/check", json={"type": "diary_event", "ids": [event_id]}).json()
    assert diary_check["warnings"][0]["label"] == "meetings that will be unlinked"
    assert diary_check["warnings"][0]["count"] == 1

    title = diary_check["titles"][0]
    assert "|" not in title
    assert "AET Weekly" in title


def test_check_references_forum_reports_full_meeting_cascade(client):
    """Deleting a forum takes its meetings with it, which in turn take their
    agenda items and decisions — the forum preflight must name all three, not
    just the meetings, by reusing the same logic the meeting branch uses."""
    session = SessionLocal()
    try:
        forum = Forum(name="Group Risk Committee", capacity_minutes=60)
        session.add(forum)
        session.flush()
        meeting = Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 7, 6, 13, 0))
        session.add(meeting)
        session.flush()
        topic = Topic(title="Risk appetite review")
        session.add(topic)
        session.flush()
        session.add(AgendaItem(meeting_id=meeting.id, topic_id=topic.id, sequence=0, allocated_minutes=15))
        session.add(Decision(meeting_id=meeting.id, title="Approved risk appetite"))
        session.commit()
        forum_id = forum.id
    finally:
        session.close()

    check = client.post("/api/bulk/check", json={"type": "forum", "ids": [forum_id]}).json()
    labels = {w["label"] for w in check["warnings"]}
    assert "meetings that will be deleted with it" in labels
    assert "agenda items that will be removed" in labels
    assert "decisions that will lose their meeting" in labels
