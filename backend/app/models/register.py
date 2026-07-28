from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text
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
