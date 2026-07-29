from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- people & workstreams ----------

class PersonMini(ORMModel):
    id: int
    name: str


class PersonIn(BaseModel):
    name: str
    email: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    is_bpm: bool = False
    active: bool = True
    notes: Optional[str] = None


class PersonPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    is_bpm: Optional[bool] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class AliasOut(ORMModel):
    id: int
    alias: str


class PersonOut(ORMModel):
    id: int
    name: str
    email: Optional[str]
    team: Optional[str]
    role: Optional[str]
    is_bpm: bool
    active: bool
    notes: Optional[str]
    aliases: list[AliasOut] = []


class WorkstreamMini(ORMModel):
    id: int
    name: str
    colour: str


class WorkstreamIn(BaseModel):
    name: str
    description: Optional[str] = None
    category: Literal["audit", "investigation", "initiative", "governance"] = "initiative"
    colour: str = "#6366f1"
    status: Literal["active", "paused", "closed"] = "active"
    owner_id: Optional[int] = None


class WorkstreamPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[Literal["audit", "investigation", "initiative", "governance"]] = None
    colour: Optional[str] = None
    status: Optional[Literal["active", "paused", "closed"]] = None
    owner_id: Optional[int] = None


class WorkstreamOut(ORMModel):
    id: int
    name: str
    description: Optional[str]
    category: str
    colour: str
    status: str
    owner: Optional[PersonMini]


# ---------- register ----------

CommitmentStatus = Literal["open", "on_track", "at_risk", "delivered", "dropped"]
ActionStatus = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
Priority = Literal["high", "medium", "low"]
Origin = Literal["principal", "aet", "external", "self"]


class CommitmentIn(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[int] = None
    origin: Origin = "principal"
    origin_detail: Optional[str] = None
    workstream_id: Optional[int] = None
    due_date: Optional[date] = None
    status: CommitmentStatus = "open"
    priority: Priority = "medium"


class CommitmentPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[int] = None
    origin: Optional[Origin] = None
    origin_detail: Optional[str] = None
    workstream_id: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[CommitmentStatus] = None
    priority: Optional[Priority] = None


class ChaseOut(ORMModel):
    id: int
    action_id: Optional[int]
    commitment_id: Optional[int]
    chased_on: date
    method: str
    note: Optional[str]
    next_chase_on: Optional[date]


class CommitmentOut(ORMModel):
    id: int
    title: str
    description: Optional[str]
    origin: str
    origin_detail: Optional[str]
    due_date: Optional[date]
    status: str
    priority: str
    owner: Optional[PersonMini]
    workstream: Optional[WorkstreamMini]
    created_at: datetime
    action_count: int = 0
    next_chase_on: Optional[date] = None


class ActionIn(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[int] = None
    commitment_id: Optional[int] = None
    workstream_id: Optional[int] = None
    due_date: Optional[date] = None
    status: ActionStatus = "todo"
    priority: Priority = "medium"
    notes: Optional[str] = None


class ActionPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[int] = None
    commitment_id: Optional[int] = None
    workstream_id: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[ActionStatus] = None
    priority: Optional[Priority] = None
    notes: Optional[str] = None


class CommitmentMini(ORMModel):
    id: int
    title: str


class ActionOut(ORMModel):
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[date]
    status: str
    priority: str
    notes: Optional[str]
    owner: Optional[PersonMini]
    commitment: Optional[CommitmentMini]
    workstream: Optional[WorkstreamMini]
    created_at: datetime
    next_chase_on: Optional[date] = None


class ChaseIn(BaseModel):
    action_id: Optional[int] = None
    commitment_id: Optional[int] = None
    chased_on: date
    method: Literal["email", "chat", "meeting"] = "email"
    note: Optional[str] = None
    next_chase_on: Optional[date] = None


class LinkIn(BaseModel):
    from_type: str
    from_id: int
    to_type: str
    to_id: int
    kind: Literal["blocks", "precedes", "informs", "relates"] = "relates"
    rationale: Optional[str] = None


class LinkOut(ORMModel):
    id: int
    from_type: str
    from_id: int
    to_type: str
    to_id: int
    kind: str
    rationale: Optional[str]


class LinkResolvedOut(LinkOut):
    """Link plus display titles for both ends, resolved server-side."""

    from_title: str = ""
    to_title: str = ""


# ---------- meetings ----------

class ForumIn(BaseModel):
    name: str
    chair_id: Optional[int] = None
    cadence: Optional[str] = None
    capacity_minutes: int = 60
    audience: Optional[str] = None
    colour: str = "#0ea5e9"


class ForumPatch(BaseModel):
    name: Optional[str] = None
    chair_id: Optional[int] = None
    cadence: Optional[str] = None
    capacity_minutes: Optional[int] = None
    audience: Optional[str] = None
    colour: Optional[str] = None


class ForumOut(ORMModel):
    id: int
    name: str
    cadence: Optional[str]
    capacity_minutes: int
    audience: Optional[str]
    colour: str
    chair: Optional[PersonMini]


class MeetingIn(BaseModel):
    forum_id: int
    scheduled_at: datetime
    status: Literal["planned", "agenda_set", "held", "cancelled"] = "planned"
    notes: Optional[str] = None


class MeetingPatch(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[Literal["planned", "agenda_set", "held", "cancelled"]] = None
    diary_event_id: Optional[str] = None
    needs_review: Optional[bool] = None
    notes: Optional[str] = None


TopicIntent = Literal["decide", "inform", "consult", "shape"]


class TopicMini(ORMModel):
    id: int
    title: str
    intent: str
    duration_minutes: int
    readiness: str
    recurring: bool = False
    sponsor: Optional[PersonMini]
    workstream: Optional[WorkstreamMini]


class AgendaItemOut(ORMModel):
    id: int
    topic_id: int
    sequence: int
    allocated_minutes: int
    outcome_note: Optional[str]
    topic: TopicMini


class MeetingOut(ORMModel):
    id: int
    forum_id: int
    scheduled_at: datetime
    status: str
    diary_event_id: Optional[str]
    needs_review: bool
    notes: Optional[str]
    forum: ForumOut
    agenda_items: list[AgendaItemOut] = []


class TopicIn(BaseModel):
    title: str
    description: Optional[str] = None
    intent: TopicIntent = "inform"
    duration_minutes: int = 15
    sponsor_id: Optional[int] = None
    workstream_id: Optional[int] = None
    commitment_id: Optional[int] = None
    readiness: Literal["draft", "ready"] = "draft"
    status: Literal["proposed", "scheduled", "discussed", "parked"] = "proposed"
    recurring: bool = False
    target_by: Optional[date] = None
    papers_url: Optional[str] = None


class TopicPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    intent: Optional[TopicIntent] = None
    duration_minutes: Optional[int] = None
    sponsor_id: Optional[int] = None
    workstream_id: Optional[int] = None
    commitment_id: Optional[int] = None
    readiness: Optional[Literal["draft", "ready"]] = None
    status: Optional[Literal["proposed", "scheduled", "discussed", "parked"]] = None
    recurring: Optional[bool] = None
    target_by: Optional[date] = None
    papers_url: Optional[str] = None


class TopicOut(ORMModel):
    id: int
    title: str
    description: Optional[str]
    intent: str
    duration_minutes: int
    readiness: str
    status: str
    recurring: bool = False
    target_by: Optional[date]
    papers_url: Optional[str]
    sponsor: Optional[PersonMini]
    workstream: Optional[WorkstreamMini]
    commitment: Optional[CommitmentMini]
    created_at: datetime


class AgendaItemIn(BaseModel):
    topic_id: int
    allocated_minutes: Optional[int] = None  # defaults to topic duration


class AgendaReorder(BaseModel):
    item_ids: list[int]  # agenda_item ids in new order


class AgendaItemPatch(BaseModel):
    allocated_minutes: Optional[int] = None
    outcome_note: Optional[str] = None


class ScoredTopic(BaseModel):
    topic: TopicOut
    score: float
    reasons: list[str]


class DecisionIn(BaseModel):
    meeting_id: Optional[int] = None
    title: str
    detail: Optional[str] = None
    decided_on: Optional[date] = None
    status: Literal["decided", "pending", "revisit"] = "decided"
    owner_id: Optional[int] = None
    review_on: Optional[date] = None


class DecisionPatch(BaseModel):
    title: Optional[str] = None
    detail: Optional[str] = None
    decided_on: Optional[date] = None
    status: Optional[Literal["decided", "pending", "revisit"]] = None
    owner_id: Optional[int] = None
    review_on: Optional[date] = None


class DecisionOut(ORMModel):
    id: int
    meeting_id: Optional[int]
    title: str
    detail: Optional[str]
    decided_on: Optional[date]
    status: str
    owner: Optional[PersonMini]
    review_on: Optional[date] = None
    created_at: datetime


# ---------- horizon ----------

class KeyDateIn(BaseModel):
    title: str
    date: date
    kind: Literal["external_deadline", "regulator", "board", "internal"] = "internal"
    hard: bool = False
    workstream_id: Optional[int] = None
    notes: Optional[str] = None


class KeyDatePatch(BaseModel):
    title: Optional[str] = None
    date: Optional[date] = None
    kind: Optional[Literal["external_deadline", "regulator", "board", "internal"]] = None
    hard: Optional[bool] = None
    workstream_id: Optional[int] = None
    notes: Optional[str] = None


class KeyDateOut(ORMModel):
    id: int
    title: str
    date: date
    kind: str
    hard: bool
    notes: Optional[str]
    workstream: Optional[WorkstreamMini]


class DiaryEventOut(ORMModel):
    id: str
    subject: Optional[str]
    start: Optional[str]
    end: Optional[str]
    start_date: Optional[str]
    start_time: Optional[str]
    end_date: Optional[str]
    end_time: Optional[str]
    organizer: Optional[str]
    required_attendees: list
    optional_attendees: list
    location: Optional[str]
    categories: list
    is_recurring: bool
    is_all_day: bool
    status: str
    cancelled_at: Optional[str]
    moved_to_event_id: Optional[str]


# ---------- ops ----------

class ModuleRunOut(ORMModel):
    id: int
    module_name: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: str
    args: Optional[str]
    log: str
    artifact_path: Optional[str]


class QuickAddIn(BaseModel):
    text: str
    type: Literal["action", "commitment", "topic"] = "action"


class ClearIn(BaseModel):
    scope: Literal["all", "demo", "diary", "module_runs"]
    confirm: str = Field(description='Must be the literal string "CLEAR"')
