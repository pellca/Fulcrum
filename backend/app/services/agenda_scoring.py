"""Rank candidate topics for a meeting with a transparent, explainable score."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import KeyDate, Topic
from ..models._mixins import utcnow


def _days_until(target: Optional[date], reference: date) -> Optional[int]:
    if target is None:
        return None
    return (target - reference).days


def score_topic(topic: Topic, meeting_date: date, hard_dates_by_ws: dict[int, list[KeyDate]]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if topic.readiness == "ready":
        score += 20
        reasons.append("Marked ready")
    if topic.intent == "decide":
        score += 15
        reasons.append("Decision needed")

    days = _days_until(topic.target_by, meeting_date)
    if days is not None:
        if days < 0:
            score += 30
            reasons.append(f"Target date passed {-days}d ago")
        elif days <= 7:
            score += 20
            reasons.append(f"Target within {days}d of meeting")
        elif days <= 14:
            score += 10
            reasons.append("Target within a fortnight")

    commitment = topic.commitment
    if commitment is not None:
        cdays = _days_until(commitment.due_date, meeting_date)
        if cdays is not None and cdays <= 14:
            score += 15
            reasons.append(f"Linked commitment due {commitment.due_date.isoformat()}")
        if commitment.status == "at_risk":
            score += 10
            reasons.append("Linked commitment at risk")

    if topic.workstream_id and topic.workstream_id in hard_dates_by_ws:
        for kd in hard_dates_by_ws[topic.workstream_id]:
            kdays = _days_until(kd.date, meeting_date)
            if kdays is not None and -7 <= kdays <= 14:
                score += 10
                reasons.append(f"Hard deadline nearby: {kd.title} ({kd.date.isoformat()})")
                break

    if topic.status == "parked":
        score += 5
        reasons.append("Previously parked")

    created = topic.created_at or utcnow()
    age_weeks = max((utcnow() - created).days, 0) // 7
    if age_weeks >= 1:
        staleness = min(age_weeks * 2, 10)
        score += staleness
        reasons.append(f"Waiting {age_weeks}w for a slot")

    return score, reasons


def rank_candidates(db: Session, meeting_at: datetime) -> list[tuple[Topic, float, list[str]]]:
    meeting_date = meeting_at.date()
    topics = (
        db.query(Topic)
        .filter(Topic.status.in_(["proposed", "parked"]))
        .all()
    )
    hard_dates = db.query(KeyDate).filter(KeyDate.hard.is_(True)).all()
    hard_by_ws: dict[int, list[KeyDate]] = {}
    for kd in hard_dates:
        if kd.workstream_id:
            hard_by_ws.setdefault(kd.workstream_id, []).append(kd)

    ranked = []
    for topic in topics:
        score, reasons = score_topic(topic, meeting_date, hard_by_ws)
        ranked.append((topic, score, reasons))
    ranked.sort(key=lambda entry: (-entry[1], entry[0].id))
    return ranked
