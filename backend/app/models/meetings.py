from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._mixins import DemoMixin, TimestampMixin
from .core import Person, Workstream
from .register import Commitment


class Forum(Base, TimestampMixin, DemoMixin):
    """A recurring governance meeting with an agenda-time budget."""

    __tablename__ = "forum"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    chair_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))
    cadence: Mapped[Optional[str]] = mapped_column(String(100))
    capacity_minutes: Mapped[int] = mapped_column(Integer, default=60)
    audience: Mapped[Optional[str]] = mapped_column(String(300))
    colour: Mapped[str] = mapped_column(String(9), default="#0ea5e9")

    chair: Mapped[Optional[Person]] = relationship()
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="forum")


class Meeting(Base, TimestampMixin, DemoMixin):
    __tablename__ = "meeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    forum_id: Mapped[int] = mapped_column(ForeignKey("forum.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    # planned | agenda_set | held | cancelled
    status: Mapped[str] = mapped_column(String(20), default="planned")
    diary_event_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("diary_event.id", ondelete="SET NULL")
    )
    # set when a linked diary event moves and the meeting auto-followed it
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    forum: Mapped[Forum] = relationship(back_populates="meetings")
    agenda_items: Mapped[list["AgendaItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="AgendaItem.sequence"
    )
    decisions: Mapped[list["Decision"]] = relationship(back_populates="meeting")


# A topic can be sponsored by several people — see workstream_owner in
# models/core.py for why this shape needs neither is_demo nor a clear scope.
topic_sponsor = Table(
    "topic_sponsor",
    Base.metadata,
    Column("topic_id", ForeignKey("topic.id", ondelete="CASCADE"), primary_key=True),
    Column("person_id", ForeignKey("person.id", ondelete="CASCADE"), primary_key=True),
)


class Topic(Base, TimestampMixin, DemoMixin):
    """A discussion item waiting for (or given) forum time."""

    __tablename__ = "topic"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # decide | inform | consult | shape
    intent: Mapped[str] = mapped_column(String(20), default="inform")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    workstream_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workstream.id", ondelete="SET NULL")
    )
    commitment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("commitment.id", ondelete="SET NULL")
    )
    # draft | ready
    readiness: Mapped[str] = mapped_column(String(10), default="draft")
    # proposed | scheduled | discussed | parked
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    # standing item: stays a candidate for every meeting, never consumed by one agenda
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    target_by: Mapped[Optional[date]] = mapped_column(Date)
    papers_url: Mapped[Optional[str]] = mapped_column(String(500))

    sponsors: Mapped[list[Person]] = relationship(secondary=topic_sponsor)
    workstream: Mapped[Optional[Workstream]] = relationship()
    commitment: Mapped[Optional[Commitment]] = relationship()


class AgendaItem(Base, TimestampMixin):
    __tablename__ = "agenda_item"
    __table_args__ = (UniqueConstraint("meeting_id", "topic_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meeting.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    allocated_minutes: Mapped[int] = mapped_column(Integer, default=15)
    outcome_note: Mapped[Optional[str]] = mapped_column(Text)

    meeting: Mapped[Meeting] = relationship(back_populates="agenda_items")
    topic: Mapped[Topic] = relationship()


class Decision(Base, TimestampMixin, DemoMixin):
    __tablename__ = "decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meeting.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    decided_on: Mapped[Optional[date]] = mapped_column(Date)
    # decided | pending | revisit
    status: Mapped[str] = mapped_column(String(20), default="decided")
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))
    # when set, the decision resurfaces on the dashboard on/after this date
    review_on: Mapped[Optional[date]] = mapped_column(Date)

    meeting: Mapped[Optional[Meeting]] = relationship(back_populates="decisions")
    owner: Mapped[Optional[Person]] = relationship()
