from typing import Optional

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MailMessage(Base):
    """Mirror of one message produced by the mail extractor. `id` is a surrogate
    integer PK (so mail rows can be targets of the generic Link table, which
    uses integer from_id/to_id); `message_id` is the extractor's stable id
    (internet-message-id, or "entryid:..." when one isn't available) used for
    idempotent upsert on import."""

    __tablename__ = "mail_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    # inbox | sent
    folder: Mapped[Optional[str]] = mapped_column(String(10))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    sender_name: Mapped[Optional[str]] = mapped_column(String(300))
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), index=True)
    to_recipients: Mapped[list] = mapped_column(JSON, default=list)
    cc_recipients: Mapped[list] = mapped_column(JSON, default=list)
    sent_at: Mapped[Optional[str]] = mapped_column(String(40))
    received_at: Mapped[Optional[str]] = mapped_column(String(40))
    # YYYY-MM-DD used for day-window filtering: received_at for inbox, sent_at for
    # sent, falling back to the other when the primary one is missing
    occurred_date: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    # pending | linked | dismissed
    triage: Mapped[str] = mapped_column(String(10), default="pending")
    triaged_at: Mapped[Optional[str]] = mapped_column(String(25))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
