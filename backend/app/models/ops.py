from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._mixins import TimestampMixin


class ModuleRun(Base, TimestampMixin):
    __tablename__ = "module_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # running | succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="running")
    args: Mapped[Optional[str]] = mapped_column(Text)
    log: Mapped[str] = mapped_column(Text, default="")
    artifact_path: Mapped[Optional[str]] = mapped_column(String(1000))
