from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._mixins import DemoMixin, TimestampMixin


class Person(Base, TimestampMixin, DemoMixin):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    team: Mapped[Optional[str]] = mapped_column(String(200))
    role: Mapped[Optional[str]] = mapped_column(String(200))
    is_bpm: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    aliases: Mapped[list["PersonAlias"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    person_notes: Mapped[list["PersonNote"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class PersonAlias(Base):
    __tablename__ = "person_alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))

    person: Mapped[Person] = relationship(back_populates="aliases")


class PersonNote(Base, TimestampMixin, DemoMixin):
    __tablename__ = "person_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    # feedback | call | observation | general
    kind: Mapped[str] = mapped_column(String(20), default="general")
    note: Mapped[str] = mapped_column(Text)
    noted_on: Mapped[date] = mapped_column(Date)
    discussed_on: Mapped[Optional[date]] = mapped_column(Date)
    # manual | mail | meeting
    source: Mapped[str] = mapped_column(String(20), default="manual")

    person: Mapped[Person] = relationship(back_populates="person_notes")


class Workstream(Base, TimestampMixin, DemoMixin):
    __tablename__ = "workstream"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # audit | investigation | initiative | governance
    category: Mapped[str] = mapped_column(String(30), default="initiative")
    colour: Mapped[str] = mapped_column(String(9), default="#6366f1")
    # active | paused | closed
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"))

    owner: Mapped[Optional[Person]] = relationship()
