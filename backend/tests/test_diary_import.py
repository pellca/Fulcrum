import json
from datetime import datetime

from app.models import DiaryEvent, Forum, Meeting, Person
from app.services.diary_import import import_diary_file

APPT = "040000008200E00074C5B7101A82E0080000000010203040"


def _event(occurrence: str, status: str = "active", **overrides) -> dict:
    base = {
        "id": f"{APPT}|{occurrence}",
        "subject": "AET Weekly",
        "startDate": occurrence[:10],
        "startTime": "10:00",
        "endDate": occurrence[:10],
        "endTime": "11:00",
        "start": f"{occurrence[:10]}T10:00:00+01:00",
        "end": f"{occurrence[:10]}T11:00:00+01:00",
        "organizer": "Alex Morgan",
        "requiredAttendees": ["Sarah Chen", "Mystery Guest"],
        "optionalAttendees": [],
        "location": "Room 4",
        "categories": ["Governance"],
        "isRecurring": True,
        "isAllDay": False,
        "status": status,
        "lastModified": "2026-07-28T09:00:00Z",
        "cancelledAt": "2026-07-28T09:00:00Z" if status == "cancelled" else None,
    }
    base.update(overrides)
    return base


def _write_diary(tmp_path, events):
    path = tmp_path / "diary.json"
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "mailbox": "cae.office@bank.com",
                    "lastRunUtc": "2026-07-28T09:00:00Z",
                    "windowFrom": "2026-07-01T00:00:00+01:00",
                    "windowTo": "2026-09-01T00:00:00+01:00",
                },
                "events": events,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_import_upsert_and_reschedule_pair(db, tmp_path):
    db.add(Person(name="Sarah Chen"))
    db.commit()

    old_slot = "2026-08-03T09:00:00Z"
    new_slot = "2026-08-04T09:00:00Z"
    path = _write_diary(
        tmp_path,
        [
            _event(old_slot, status="cancelled"),
            _event(new_slot, status="active"),
            {**_event("2026-08-10T09:00:00Z"), "id": "OTHERAPPT|2026-08-10T09:00:00Z"},
        ],
    )
    summary = import_diary_file(db, path)

    assert summary["added"] == 3
    assert summary["moved_pairs"] == 1
    assert summary["mailbox"] == "cae.office@bank.com"
    # unknown display name is surfaced, known one isn't
    assert "Mystery Guest" in summary["unmatched_attendees"]
    assert "Sarah Chen" not in summary["unmatched_attendees"]

    cancelled = db.get(DiaryEvent, f"{APPT}|{old_slot}")
    assert cancelled.moved_to_event_id == f"{APPT}|{new_slot}"

    # second import of identical file changes nothing
    summary2 = import_diary_file(db, path)
    assert summary2["added"] == 0 and summary2["unchanged"] == 3


def test_linked_meeting_follows_move(db, tmp_path):
    old_slot = "2026-08-03T09:00:00Z"
    new_slot = "2026-08-05T14:00:00Z"

    forum = Forum(name="AET Weekly", capacity_minutes=60)
    db.add(forum)
    db.flush()
    meeting = Meeting(
        forum_id=forum.id,
        scheduled_at=datetime(2026, 8, 3, 10, 0),
        diary_event_id=None,
    )
    db.add(meeting)
    db.commit()

    # first import: link meeting to the (then-active) occurrence
    path = _write_diary(tmp_path, [_event(old_slot)])
    import_diary_file(db, path)
    meeting.diary_event_id = f"{APPT}|{old_slot}"
    db.commit()

    # second import: occurrence cancelled and re-created at a new slot
    path = _write_diary(
        tmp_path,
        [
            _event(old_slot, status="cancelled"),
            _event(new_slot, start=f"2026-08-05T14:00:00+01:00", startTime="14:00"),
        ],
    )
    summary = import_diary_file(db, path)

    assert summary["meetings_updated"] == 1
    db.refresh(meeting)
    assert meeting.diary_event_id == f"{APPT}|{new_slot}"
    assert meeting.needs_review is True
    assert meeting.scheduled_at == datetime(2026, 8, 5, 14, 0)


def test_rejects_non_diary_json(db, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"foo": 1}', encoding="utf-8")
    try:
        import_diary_file(db, path)
        raise AssertionError("should have raised")
    except ValueError as exc:
        assert "events" in str(exc)
