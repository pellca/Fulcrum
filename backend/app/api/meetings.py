from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import AgendaItem, Decision, DiaryEvent, Forum, Meeting, Topic
from ..schemas import (
    AgendaItemIn,
    AgendaItemPatch,
    AgendaReorder,
    DecisionIn,
    DecisionOut,
    DecisionPatch,
    ForumIn,
    ForumOut,
    ForumPatch,
    MeetingIn,
    MeetingOut,
    MeetingPatch,
    RollingAgendaOut,
    ScoredTopic,
    TopicIn,
    TopicOut,
    TopicPatch,
)
from ..services.agenda_scoring import rank_candidates
from ..services.bulk import delete_entities, resolve_people

router = APIRouter(tags=["meetings"])


# ---------- forums ----------

@router.get("/forums", response_model=list[ForumOut])
def list_forums(db: Session = Depends(get_db)):
    return db.query(Forum).order_by(Forum.name).all()


@router.post("/forums", response_model=ForumOut, status_code=201)
def create_forum(body: ForumIn, db: Session = Depends(get_db)):
    forum = Forum(**body.model_dump())
    db.add(forum)
    db.commit()
    return forum


@router.patch("/forums/{forum_id}", response_model=ForumOut)
def update_forum(forum_id: int, body: ForumPatch, db: Session = Depends(get_db)):
    forum = db.get(Forum, forum_id)
    if not forum:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(forum, key, value)
    db.commit()
    return forum


@router.delete("/forums/{forum_id}", status_code=204)
def delete_forum(forum_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "forum", [forum_id])


@router.get("/forums/{forum_id}/rolling-agenda", response_model=RollingAgendaOut)
def rolling_agenda(
    forum_id: int,
    limit: int = Query(8, ge=1, le=24),
    include_past: bool = False,
    db: Session = Depends(get_db),
):
    """Single-pane-of-glass forward view for one forum: the agendas of its next
    `limit` meetings side by side, pivoted so a row is a topic and a column is a
    meeting. A `recurring` standing item legitimately sits on many meetings, so
    it produces one row with several filled cells rather than several rows.

    `include_past=false` (default) reuses the exact expression `list_meetings`
    uses for `upcoming_only` (`scheduled_at >= now - 12h`), so this view and the
    plain meetings list never disagree about what counts as "upcoming".
    `include_past=true` returns the earliest `limit` meetings of the forum,
    past or future. `limit` is bounded to 1-24 (enforced, not silently clamped
    — see OpenAPI).

    Loader chain (constant number of statements regardless of how many meetings
    or agenda items exist) — 6 SELECTs, or 7 when at least one of the returned
    meetings has a diary link:
      1. `db.get(Forum, ...)` for the forum
      2. the meetings query itself
      3. `selectinload(Meeting.agenda_items)` for every agenda item on those
         meetings, in one batch
      4. `selectinload(AgendaItem.topic)` for the distinct topics referenced,
         in one batch
      5. `selectinload(Topic.sponsors)` for the sponsors of the distinct topics,
         in one batch (many-to-many, still a single SELECT through the join table)
      6. `selectinload(Topic.workstream)` for the distinct workstreams
         referenced, in one batch
      7. (conditional) one `DiaryEvent.id.in_(...)` batch query (id, location
         only) for the linked diary events, to fill in
         `RollingMeetingOut.location`
    """
    forum = db.get(Forum, forum_id)
    if not forum:
        raise HTTPException(404)

    query = db.query(Meeting).filter(Meeting.forum_id == forum_id)
    if not include_past:
        query = query.filter(Meeting.scheduled_at >= datetime.now() - timedelta(hours=12))
    meetings = (
        query.options(
            selectinload(Meeting.agenda_items)
            .selectinload(AgendaItem.topic)
            .selectinload(Topic.sponsors),
            selectinload(Meeting.agenda_items)
            .selectinload(AgendaItem.topic)
            .selectinload(Topic.workstream),
        )
        .order_by(Meeting.scheduled_at)
        .limit(limit)
        .all()
    )

    diary_ids = [m.diary_event_id for m in meetings if m.diary_event_id]
    locations: dict[str, Optional[str]] = {}
    if diary_ids:
        locations = dict(
            db.query(DiaryEvent.id, DiaryEvent.location)
            .filter(DiaryEvent.id.in_(diary_ids))
            .all()
        )

    n = len(meetings)
    meeting_index = {m.id: idx for idx, m in enumerate(meetings)}
    meetings_out = [
        {
            "id": m.id,
            "scheduled_at": m.scheduled_at,
            "status": m.status,
            "diary_event_id": m.diary_event_id,
            "needs_review": m.needs_review,
            "location": locations.get(m.diary_event_id) if m.diary_event_id else None,
            "allocated_minutes": sum(item.allocated_minutes for item in m.agenda_items),
            "capacity_minutes": forum.capacity_minutes,
            "item_count": len(m.agenda_items),
        }
        for m in meetings
    ]

    # pivot: one row per topic, cells positionally aligned to `meetings_out`
    topic_rows: dict[int, dict] = {}
    for m in meetings:
        idx = meeting_index[m.id]
        for item in m.agenda_items:
            topic = item.topic
            row = topic_rows.get(topic.id)
            if row is None:
                row = {"topic": topic, "cells": [None] * n, "first_idx": idx}
                topic_rows[topic.id] = row
            row["cells"][idx] = {
                "agenda_item_id": item.id,
                "meeting_id": m.id,
                "sequence": item.sequence,
                "allocated_minutes": item.allocated_minutes,
                "outcome_note": item.outcome_note,
            }

    bands: dict[Optional[int], dict] = {}
    for row in topic_rows.values():
        workstream = row["topic"].workstream
        key = workstream.id if workstream else None
        band = bands.get(key)
        if band is None:
            band = {
                "workstream": workstream,
                "label": workstream.name if workstream else "Unassigned",
                "category": workstream.category if workstream else None,
                "rows": [],
            }
            bands[key] = band
        band["rows"].append(row)

    for band in bands.values():
        band["rows"].sort(key=lambda r: (r["first_idx"], r["topic"].title))

    bands_out = [
        {
            "workstream": band["workstream"],
            "label": band["label"],
            "category": band["category"],
            "rows": [{"topic": r["topic"], "cells": r["cells"]} for r in band["rows"]],
        }
        for band in sorted(
            bands.values(),
            # unassigned last; sort_order is 0 until set by hand, so untouched
            # data falls back to the category/label order that predates it
            key=lambda b: (
                b["workstream"] is None,
                b["workstream"].sort_order if b["workstream"] else 0,
                b["category"] or "",
                b["label"],
            ),
        )
    ]

    return {"forum": forum, "meetings": meetings_out, "bands": bands_out}


# ---------- meetings ----------

@router.get("/meetings", response_model=list[MeetingOut])
def list_meetings(
    forum_id: Optional[int] = None,
    upcoming_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Meeting)
    if forum_id:
        query = query.filter(Meeting.forum_id == forum_id)
    if upcoming_only:
        from datetime import datetime, timedelta

        query = query.filter(Meeting.scheduled_at >= datetime.now() - timedelta(hours=12))
    return query.order_by(Meeting.scheduled_at).all()


@router.post("/meetings", response_model=MeetingOut, status_code=201)
def create_meeting(body: MeetingIn, db: Session = Depends(get_db)):
    if not db.get(Forum, body.forum_id):
        raise HTTPException(422, "Unknown forum")
    meeting = Meeting(**body.model_dump())
    db.add(meeting)
    db.commit()
    return meeting


@router.get("/meetings/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404)
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(meeting_id: int, body: MeetingPatch, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(meeting, key, value)
    db.commit()
    return meeting


@router.delete("/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "meeting", [meeting_id])


# ---------- agenda ----------

@router.get("/meetings/{meeting_id}/candidates", response_model=list[ScoredTopic])
def agenda_candidates(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404)
    on_agenda = {item.topic_id for item in meeting.agenda_items}
    ranked = rank_candidates(db, meeting.scheduled_at)
    return [
        {"topic": topic, "score": score, "reasons": reasons}
        for topic, score, reasons in ranked
        if topic.id not in on_agenda
    ]


@router.post("/meetings/{meeting_id}/agenda", response_model=MeetingOut)
def add_agenda_item(meeting_id: int, body: AgendaItemIn, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    topic = db.get(Topic, body.topic_id)
    if not meeting or not topic:
        raise HTTPException(404)
    if any(item.topic_id == topic.id for item in meeting.agenda_items):
        raise HTTPException(409, "Topic already on agenda")
    sequence = max((item.sequence for item in meeting.agenda_items), default=0) + 1
    db.add(
        AgendaItem(
            meeting_id=meeting_id,
            topic_id=topic.id,
            sequence=sequence,
            allocated_minutes=body.allocated_minutes or topic.duration_minutes,
        )
    )
    if not topic.recurring:  # standing items are never consumed by one agenda
        topic.status = "scheduled"
    db.commit()
    db.refresh(meeting)
    return meeting


@router.post("/meetings/{meeting_id}/agenda/reorder", response_model=MeetingOut)
def reorder_agenda(meeting_id: int, body: AgendaReorder, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404)
    order = {item_id: index + 1 for index, item_id in enumerate(body.item_ids)}
    for item in meeting.agenda_items:
        if item.id in order:
            item.sequence = order[item.id]
    db.commit()
    db.refresh(meeting)
    return meeting


@router.patch("/agenda-items/{item_id}", response_model=MeetingOut)
def update_agenda_item(item_id: int, body: AgendaItemPatch, db: Session = Depends(get_db)):
    item = db.get(AgendaItem, item_id)
    if not item:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    return db.get(Meeting, item.meeting_id)


@router.delete("/agenda-items/{item_id}", status_code=204)
def remove_agenda_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(AgendaItem, item_id)
    if item:
        topic = db.get(Topic, item.topic_id)
        if topic and topic.status == "scheduled":
            topic.status = "proposed"
        db.delete(item)
        db.commit()


# ---------- topics ----------

@router.get("/topics", response_model=list[TopicOut])
def list_topics(
    status: Optional[str] = None,
    workstream_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Topic).options(selectinload(Topic.sponsors))
    if status:
        query = query.filter(Topic.status == status)
    if workstream_id:
        query = query.filter(Topic.workstream_id == workstream_id)
    return query.order_by(Topic.created_at.desc()).all()


@router.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(body: TopicIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    sponsors = resolve_people(db, data.pop("sponsor_ids"))
    topic = Topic(**data)
    topic.sponsors = sponsors
    db.add(topic)
    db.commit()
    return topic


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicPatch, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "sponsor_ids":
            topic.sponsors = resolve_people(db, value or [])
        else:
            setattr(topic, key, value)
    db.commit()
    return topic


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "topic", [topic_id])


# ---------- decisions ----------

@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(meeting_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Decision)
    if meeting_id:
        query = query.filter(Decision.meeting_id == meeting_id)
    return query.order_by(Decision.created_at.desc()).all()


@router.post("/decisions", response_model=DecisionOut, status_code=201)
def create_decision(body: DecisionIn, db: Session = Depends(get_db)):
    decision = Decision(**body.model_dump())
    db.add(decision)
    db.commit()
    return decision


@router.patch("/decisions/{decision_id}", response_model=DecisionOut)
def update_decision(decision_id: int, body: DecisionPatch, db: Session = Depends(get_db)):
    decision = db.get(Decision, decision_id)
    if not decision:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(decision, key, value)
    db.commit()
    return decision


@router.delete("/decisions/{decision_id}", status_code=204)
def delete_decision(decision_id: int, db: Session = Depends(get_db)):
    delete_entities(db, "decision", [decision_id])
