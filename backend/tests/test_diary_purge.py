from datetime import datetime

from app.db import SessionLocal
from app.models import DiaryEvent, Forum, Meeting


def _add_event(session, event_id, subject, start_date, start_time, status="active"):
    session.add(
        DiaryEvent(
            id=event_id, subject=subject, start_date=start_date, start_time=start_time, status=status
        )
    )


def test_preview_counts_match_delete_result(client):
    session = SessionLocal()
    try:
        forum = Forum(name="AET Weekly", capacity_minutes=60)
        session.add(forum)
        session.flush()
        _add_event(session, "E1", "AET Weekly", "2026-07-01", "10:00")
        _add_event(session, "E2", "Budget Review", "2026-07-15", "09:00")
        _add_event(session, "E3", "Out of range", "2026-08-01", "09:00")
        session.flush()
        meeting = Meeting(forum_id=forum.id, scheduled_at=datetime(2026, 7, 1, 10, 0), diary_event_id="E1")
        session.add(meeting)
        session.commit()
        meeting_id = meeting.id
    finally:
        session.close()

    body = {"from_date": "2026-07-01", "to_date": "2026-07-31", "include_cancelled": True}
    preview = client.post("/api/diary/purge-preview", json=body).json()
    assert preview["events"] == 2
    assert preview["linked_meetings"] == 1
    assert len(preview["examples"]) == 2
    assert preview["meeting_examples"] == ["AET Weekly — 01 Jul 2026"]

    result = client.post("/api/diary/purge", json={**body, "confirm": "DELETE"}).json()
    assert result["deleted"] == preview["events"]
    assert result["meetings_unlinked"] == preview["linked_meetings"]

    session = SessionLocal()
    try:
        remaining = session.query(DiaryEvent).all()
        assert [e.id for e in remaining] == ["E3"]
        m = session.get(Meeting, meeting_id)
        assert m is not None
        assert m.diary_event_id is None
    finally:
        session.close()


def test_include_cancelled_false_spares_cancelled_events(client):
    session = SessionLocal()
    try:
        _add_event(session, "E1", "Active event", "2026-07-01", "10:00", status="active")
        _add_event(session, "E2", "Cancelled event", "2026-07-02", "10:00", status="cancelled")
        session.commit()
    finally:
        session.close()

    result = client.post(
        "/api/diary/purge",
        json={
            "from_date": "2026-07-01",
            "to_date": "2026-07-31",
            "include_cancelled": False,
            "confirm": "DELETE",
        },
    ).json()
    assert result["deleted"] == 1

    session = SessionLocal()
    try:
        remaining = [e.id for e in session.query(DiaryEvent).all()]
        assert remaining == ["E2"]
    finally:
        session.close()


def test_purge_validation_errors(client):
    good = {"from_date": "2026-07-01", "to_date": "2026-07-31", "include_cancelled": True, "confirm": "DELETE"}

    bad_format = {**good, "from_date": "01-07-2026"}
    assert client.post("/api/diary/purge", json=bad_format).status_code == 422

    reversed_range = {**good, "from_date": "2026-08-01", "to_date": "2026-07-01"}
    assert client.post("/api/diary/purge", json=reversed_range).status_code == 422

    wrong_confirm = {**good, "confirm": "nope"}
    assert client.post("/api/diary/purge", json=wrong_confirm).status_code == 422


def test_purge_empty_range_is_a_no_op(client):
    resp = client.post(
        "/api/diary/purge",
        json={
            "from_date": "2099-01-01",
            "to_date": "2099-01-31",
            "include_cancelled": True,
            "confirm": "DELETE",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0, "meetings_unlinked": 0}
