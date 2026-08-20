"""Auto-suggest links between Meetings and DiaryEvents, and one-click creation
of a Meeting from a DiaryEvent.

`score_pair` is a pure function (no DB, no HTTP) so it can be unit-tested
directly against a table of (forum name, subject, times) -> expected verdict.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from ..models import DiaryEvent, Forum, Meeting

STOPWORDS = {
    "meeting", "mtg", "call", "weekly", "monthly", "fortnightly", "quarterly",
    "the", "and", "for", "with", "invite", "tentative", "fw", "fwd", "re",
    "committee",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.casefold())


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) >= 3 and t not in STOPWORDS}


def _acronym(text: str) -> Optional[str]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if len(words) < 2:
        return None
    letters = "".join(w[0] for w in words if w[0].isalnum())
    return letters.casefold() if len(letters) >= 2 else None


def event_local_datetime(event: DiaryEvent) -> Optional[datetime]:
    """Naive local datetime from the wall-clock start_date/start_time columns.

    CRITICAL: never parse from `event.start` — that ISO string currently
    carries a wrong timezone offset (separate fix in flight), while
    start_date/start_time are correct. Meeting.scheduled_at is naive local,
    so wall-clock-to-wall-clock comparison is both simpler and immune to
    that bug.
    """
    if event.start_date and event.start_time:
        try:
            return datetime.strptime(f"{event.start_date} {event.start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    if event.start:
        try:
            return datetime.fromisoformat(event.start).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def score_pair(
    forum_name: str,
    subject: Optional[str],
    meeting_dt: datetime,
    event_dt: datetime,
    within_minutes: int,
) -> Optional[tuple[float, list[str]]]:
    """Pure scoring function. Returns None if either hard gate fails."""
    subject = subject or ""

    # Gate 1: time. Same calendar day and within `within_minutes` minutes.
    if meeting_dt.date() != event_dt.date():
        return None
    minutes_apart = abs((meeting_dt - event_dt).total_seconds()) / 60
    if minutes_apart > within_minutes:
        return None

    reasons: list[str] = []

    # Gate 2: subject.
    norm_forum = _normalise(forum_name)
    norm_subject = _normalise(subject)

    contains = bool(norm_forum) and bool(norm_subject) and (
        norm_forum in norm_subject or norm_subject in norm_forum
    )

    forum_tokens = _significant_tokens(forum_name)
    subject_tokens = _significant_tokens(subject)
    union = forum_tokens | subject_tokens
    intersection = forum_tokens & subject_tokens
    jaccard = (len(intersection) / len(union)) if union else 0.0
    token_hit = len(intersection) >= 1 and jaccard >= 0.34

    forum_acronym = _acronym(forum_name)
    subject_acronym = _acronym(subject)
    acronym_hit = False
    acronym_value = None
    if forum_acronym and forum_acronym in subject_tokens:
        acronym_hit = True
        acronym_value = forum_acronym
    elif subject_acronym and subject_acronym in forum_tokens:
        acronym_hit = True
        acronym_value = subject_acronym

    if not (contains or token_hit or acronym_hit):
        return None

    if contains:
        reasons.append("Title match")
        jaccard = max(jaccard, 0.6)
    if token_hit and "Title match" not in reasons:
        reasons.append("Similar title")
    if acronym_hit:
        reasons.append(f"Acronym match ({acronym_value.upper()})")
        jaccard = max(jaccard, 0.6)

    if minutes_apart == 0:
        reasons.insert(0, f"Same {meeting_dt:%H:%M} slot")
    else:
        reasons.insert(0, f"{int(round(minutes_apart))} min apart")

    time_score = 40 * max(0.0, 1 - minutes_apart / within_minutes) if within_minutes else 0.0
    subject_score = 60 * jaccard
    score = time_score + subject_score
    return score, reasons


def suggest_links(db: Session, limit: int = 25, within_minutes: int = 120) -> list[dict]:
    meetings = (
        db.query(Meeting)
        .filter(Meeting.diary_event_id.is_(None), Meeting.status != "cancelled")
        .options(selectinload(Meeting.forum))
        .all()
    )
    if not meetings:
        return []

    linked_event_ids = {
        m.diary_event_id
        for m in db.query(Meeting).filter(Meeting.diary_event_id.isnot(None)).all()
    }
    events = db.query(DiaryEvent).filter(DiaryEvent.status == "active").all()
    events = [e for e in events if e.id not in linked_event_ids]
    if not events:
        return []

    # score_pair's first hard gate is same-calendar-day, so bucket events by
    # date once up front rather than rescoring every meeting x event pair.
    events_by_date: dict = defaultdict(list)
    for e in events:
        dt = event_local_datetime(e)
        if dt:
            events_by_date[dt.date()].append((e, dt))

    candidates = []
    for meeting in meetings:
        forum = meeting.forum
        if forum is None:
            continue
        for event, event_dt in events_by_date.get(meeting.scheduled_at.date(), []):
            result = score_pair(forum.name, event.subject, meeting.scheduled_at, event_dt, within_minutes)
            if result is None:
                continue
            score, reasons = result
            if score < 45:
                continue
            candidates.append((score, meeting, event, event_dt, reasons))

    # Greedy one-to-one assignment: highest score first, each meeting/event used once.
    candidates.sort(key=lambda c: c[0], reverse=True)
    used_meetings: set[int] = set()
    used_events: set[str] = set()
    suggestions = []
    for score, meeting, event, event_dt, reasons in candidates:
        if meeting.id in used_meetings or event.id in used_events:
            continue
        used_meetings.add(meeting.id)
        used_events.add(event.id)
        minutes_apart = abs((meeting.scheduled_at - event_dt).total_seconds()) / 60
        suggestions.append(
            {
                "meeting_id": meeting.id,
                "forum_name": meeting.forum.name,
                "forum_colour": meeting.forum.colour,
                "scheduled_at": meeting.scheduled_at,
                "diary_event_id": event.id,
                "subject": event.subject,
                "event_start_date": event.start_date,
                "event_start_time": event.start_time,
                "location": event.location,
                "minutes_apart": minutes_apart,
                "score": round(score, 1),
                "confidence": "high" if score >= 70 and any(
                    r == "Title match" or r.startswith("Acronym match") for r in reasons
                ) else "likely",
                "reasons": reasons,
            }
        )
        if len(suggestions) >= limit:
            break

    return suggestions


class DiaryLinkConflict(Exception):
    """Raised when the diary event already has a meeting linked to it (-> 409)."""


def create_meeting_from_event(db: Session, body) -> Meeting:
    """Implements POST /diary/create-meeting. `body` is DiaryCreateMeetingIn.

    Raises LookupError for an unknown diary event (-> 404 in the endpoint),
    DiaryLinkConflict if the event is already linked (-> 409), ValueError for
    bad forum arguments (-> 422).
    """
    event = db.get(DiaryEvent, body.diary_event_id)
    if not event:
        raise LookupError("Unknown diary event")

    existing = db.query(Meeting).filter(Meeting.diary_event_id == event.id).first()
    if existing:
        raise DiaryLinkConflict("A meeting is already linked to this diary event")

    has_forum_id = body.forum_id is not None
    has_new_name = bool(body.new_forum_name and body.new_forum_name.strip())
    if has_forum_id == has_new_name:
        raise ValueError("Provide exactly one of forum_id or new_forum_name")

    if has_forum_id:
        forum = db.get(Forum, body.forum_id)
        if not forum:
            raise ValueError("Unknown forum_id")
    else:
        capacity_minutes = body.new_forum_capacity_minutes
        if capacity_minutes is None:
            start_dt = event_local_datetime(event)
            end_dt = None
            if event.end_date and event.end_time:
                try:
                    end_dt = datetime.strptime(f"{event.end_date} {event.end_time}", "%Y-%m-%d %H:%M")
                except ValueError:
                    end_dt = None
            if start_dt and end_dt:
                duration = int(round((end_dt - start_dt).total_seconds() / 60))
                capacity_minutes = max(15, min(480, duration))
            else:
                capacity_minutes = 60
        forum = Forum(
            name=body.new_forum_name.strip(),
            colour=body.new_forum_colour,
            capacity_minutes=capacity_minutes,
        )
        db.add(forum)
        db.flush()

    scheduled_at = event_local_datetime(event)
    if scheduled_at is None:
        raise ValueError("Diary event has no parseable start time")

    meeting = Meeting(
        forum_id=forum.id,
        scheduled_at=scheduled_at,
        status=body.status,
        diary_event_id=event.id,
        needs_review=False,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting
