from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._mixins import DemoMixin, TimestampMixin
from .core import Person, Workstream


class Commitment(Base, TimestampMixin, DemoMixin):
    __tablename__ = "commitment"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))
    # principal | aet | external | self
    origin: Mapped[str] = mapped_column(String(20), default="principal")
    origin_detail: Mapped[Optional[str]] = mapped_column(String(300))
    workstream_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workstream.id", ondelete="SET NULL")
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    # open | on_track | at_risk | delivered | dropped
    status: Mapped[str] = mapped_column(String(20), default="open")
    # high | medium | low
    priority: Mapped[str] = mapped_column(String(10), default="medium")

    owner: Mapped[Optional[Person]] = relationship()
    workstream: Mapped[Optional[Workstream]] = relationship()
    actions: Mapped[list["Action"]] = relationship(back_populates="commitment")


class Action(Base, TimestampMixin, DemoMixin):
    __tablename__ = "action"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))
    commitment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("commitment.id", ondelete="SET NULL")
    )
    workstream_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workstream.id", ondelete="SET NULL")
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    # todo | in_progress | blocked | done | cancelled
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    owner: Mapped[Optional[Person]] = relationship()
    commitment: Mapped[Optional[Commitment]] = relationship(back_populates="actions")
    workstream: Mapped[Optional[Workstream]] = relationship()
    chases: Mapped[list["Chase"]] = relationship(
        back_populates="action", cascade="all, delete-orphan"
    )


class Chase(Base, TimestampMixin):
    """A nudge sent to keep an action/commitment on track; next_chase_on drives the queue."""

    __tablename__ = "chase"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[Optional[int]] = mapped_column(ForeignKey("action.id", ondelete="CASCADE"))
    commitment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("commitment.id", ondelete="CASCADE")
    )
    chased_on: Mapped[date] = mapped_column(Date)
    # email | chat | meeting
    method: Mapped[str] = mapped_column(String(20), default="email")
    note: Mapped[Optional[str]] = mapped_column(Text)
    next_chase_on: Mapped[Optional[date]] = mapped_column(Date)

    action: Mapped[Optional[Action]] = relationship(back_populates="chases")
    commitment: Mapped[Optional[Commitment]] = relationship()


class DiscussionPoint(Base, TimestampMixin, DemoMixin):
    """Something to raise with one person on the next call.

    Deliberately not an Action (nobody owes work), a Commitment (nothing was
    promised) or a PersonNote (that records an observation *about* someone, not
    an item *for* a conversation). What it points at, if anything, is a Link
    edge rather than a column, so one point can reference an action, a
    commitment and a person at once — or nothing at all, which is the common
    case for "ask Paul about the headcount freeze".

    `last_discussed_on` and `status` are separate on purpose: covering a point
    is not the same event as being finished with it. A standing item gets
    stamped every week and never closes; a one-off is raised once and closed.
    Keeping them apart is what lets the list sort stalest-first.
    """

    __tablename__ = "discussion_point"

    id: Mapped[int] = mapped_column(primary_key=True)
    # the list this belongs to; CASCADE because the point has no meaning without
    # the person (delete_entities warns before it happens — see bulk.py)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    # high | medium | low
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    # open | closed
    status: Mapped[str] = mapped_column(String(20), default="open")
    raised_on: Mapped[date] = mapped_column(Date)
    last_discussed_on: Mapped[Optional[date]] = mapped_column(Date)
    times_discussed: Mapped[int] = mapped_column(Integer, default=0)
    closed_on: Mapped[Optional[date]] = mapped_column(Date)
    outcome: Mapped[Optional[str]] = mapped_column(Text)

    person: Mapped[Person] = relationship()


class Link(Base, TimestampMixin):
    """Generic edge between any two entities. kind: blocks | precedes | informs | relates."""

    __tablename__ = "link"
    __table_args__ = (
        Index("ix_link_from", "from_type", "from_id"),
        Index("ix_link_to", "to_type", "to_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_type: Mapped[str] = mapped_column(String(30))
    from_id: Mapped[int] = mapped_column()
    to_type: Mapped[str] = mapped_column(String(30))
    to_id: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(20), default="relates")
    rationale: Mapped[Optional[str]] = mapped_column(Text)
