from datetime import date
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._mixins import DemoMixin, TimestampMixin
from .core import Workstream


class KeyDate(Base, TimestampMixin, DemoMixin):
    __tablename__ = "key_date"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    date: Mapped[date] = mapped_column(Date)
    # external_deadline | regulator | board | internal
    kind: Mapped[str] = mapped_column(String(30), default="internal")
    hard: Mapped[bool] = mapped_column(Boolean, default=False)
    workstream_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workstream.id", ondelete="SET NULL")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    workstream: Mapped[Optional[Workstream]] = relationship()


class DiaryEvent(Base):
    """Mirror of one OutlookDiaryExtractor event; PK is the extractor's stable id
    (`<GlobalAppointmentID>|<occurrenceStartUtc>`)."""

    __tablename__ = "diary_event"

    id: Mapped[str] = mapped_column(String(400), primary_key=True)
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    start: Mapped[Optional[str]] = mapped_column(String(40))  # ISO with local offset
    end: Mapped[Optional[str]] = mapped_column(String(40))
    start_date: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    start_time: Mapped[Optional[str]] = mapped_column(String(5))
    end_date: Mapped[Optional[str]] = mapped_column(String(10))
    end_time: Mapped[Optional[str]] = mapped_column(String(5))
    organizer: Mapped[Optional[str]] = mapped_column(String(300))
    required_attendees: Mapped[list] = mapped_column(JSON, default=list)
    optional_attendees: Mapped[list] = mapped_column(JSON, default=list)
    location: Mapped[Optional[str]] = mapped_column(String(500))
    categories: Mapped[list] = mapped_column(JSON, default=list)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    # active | cancelled
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_modified: Mapped[Optional[str]] = mapped_column(String(25))
    cancelled_at: Mapped[Optional[str]] = mapped_column(String(25))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # reschedule-pair detection: cancelled occurrence -> its replacement
    moved_to_event_id: Mapped[Optional[str]] = mapped_column(String(400))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
