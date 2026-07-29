from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AgendaItem, Decision, Forum, Meeting, Topic
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
    ScoredTopic,
    TopicIn,
    TopicOut,
    TopicPatch,
)
from ..services.agenda_scoring import rank_candidates

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
    forum = db.get(Forum, forum_id)
    if forum:
        db.delete(forum)
        db.commit()


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
    meeting = db.get(Meeting, meeting_id)
    if meeting:
        db.delete(meeting)
        db.commit()


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
    query = db.query(Topic)
    if status:
        query = query.filter(Topic.status == status)
    if workstream_id:
        query = query.filter(Topic.workstream_id == workstream_id)
    return query.order_by(Topic.created_at.desc()).all()


@router.post("/topics", response_model=TopicOut, status_code=201)
def create_topic(body: TopicIn, db: Session = Depends(get_db)):
    topic = Topic(**body.model_dump())
    db.add(topic)
    db.commit()
    return topic


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicPatch, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(topic, key, value)
    db.commit()
    return topic


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if topic:
        db.delete(topic)
        db.commit()


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
    decision = db.get(Decision, decision_id)
    if decision:
        db.delete(decision)
        db.commit()
