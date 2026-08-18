"""pytest suite for the pure mail-normalization logic in mail_normalize.py.

Run from the repo root:
    cd /home/cp/Dev/CoS && .venv/bin/python -m pytest tools/mail_extractor/tests -q

No COM / pywin32 involved anywhere in this file or in mail_normalize.py, so
it runs on any OS.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Make mail_normalize importable when pytest is invoked from the repo root
# (mirrors OutlookDiaryExtractor/tests/test_merge.py's sys.path handling).
_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

import mail_normalize  # noqa: E402


# ---------------------------------------------------------------------------
#  No-COM guarantee
# ---------------------------------------------------------------------------

def test_mail_normalize_module_has_no_com_import():
    """The pure layer must never import win32com, on any platform."""
    assert "win32com" not in sys.modules
    assert "win32com.client" not in sys.modules


def test_export_mail_imports_without_com_on_linux():
    """export_mail.py imports pywin32 lazily inside _attach_to_outlook, so
    the module itself must import cleanly here (Linux, no pywin32) without
    ever touching win32com at import time."""
    if _TOOL_DIR not in sys.path:
        sys.path.insert(0, _TOOL_DIR)
    import export_mail  # noqa: F401
    assert "win32com" not in sys.modules
    # CLI parser should build and parse without touching COM either.
    parser = export_mail._build_parser()
    args = parser.parse_args(["--days", "7", "--out", "x.json"])
    assert args.days == 7
    assert args.out == "x.json"
    assert args.mailbox == ""


# ---------------------------------------------------------------------------
#  iso_utc / iso_local_offset
# ---------------------------------------------------------------------------

def test_iso_utc_format():
    dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert mail_normalize.iso_utc(dt) == "2026-08-18T12:00:00Z"


def test_iso_utc_converts_offset_to_utc():
    tz = timezone(timedelta(hours=1))
    dt = datetime(2026, 8, 18, 13, 0, 0, tzinfo=tz)  # 12:00 UTC
    assert mail_normalize.iso_utc(dt) == "2026-08-18T12:00:00Z"


def test_iso_local_offset_positive():
    tz = timezone(timedelta(hours=1))
    dt = datetime(2026, 8, 18, 14, 0, 0, tzinfo=tz)
    assert mail_normalize.iso_local_offset(dt) == "2026-08-18T14:00:00+01:00"


def test_iso_local_offset_negative():
    tz = timezone(timedelta(hours=-5))
    dt = datetime(2026, 8, 18, 9, 30, 0, tzinfo=tz)
    assert mail_normalize.iso_local_offset(dt) == "2026-08-18T09:30:00-05:00"


def test_iso_local_offset_none_is_none():
    assert mail_normalize.iso_local_offset(None) is None


# ---------------------------------------------------------------------------
#  truncate_body
# ---------------------------------------------------------------------------

def test_truncate_body_under_limit_unchanged():
    text = "hello world"
    assert mail_normalize.truncate_body(text) == text


def test_truncate_body_over_limit_capped():
    text = "x" * 40000
    out = mail_normalize.truncate_body(text)
    assert len(out) == mail_normalize.BODY_MAX_CHARS == 32000
    assert out == "x" * 32000


def test_truncate_body_exact_limit_unchanged():
    text = "y" * 32000
    out = mail_normalize.truncate_body(text)
    assert len(out) == 32000
    assert out == text


def test_truncate_body_none_becomes_empty_string():
    assert mail_normalize.truncate_body(None) == ""


# ---------------------------------------------------------------------------
#  recipients
# ---------------------------------------------------------------------------

def test_normalize_recipient_basic():
    assert mail_normalize.normalize_recipient("Alice", "alice@x.com") == {
        "name": "Alice", "email": "alice@x.com"}


def test_normalize_recipient_missing_fields_become_empty_string():
    assert mail_normalize.normalize_recipient(None, None) == {"name": "", "email": ""}
    assert mail_normalize.normalize_recipient("", "") == {"name": "", "email": ""}


def test_normalize_recipients_from_tuples():
    raw = [("Alice", "alice@x.com"), ("Bob", "")]
    out = mail_normalize.normalize_recipients(raw)
    assert out == [
        {"name": "Alice", "email": "alice@x.com"},
        {"name": "Bob", "email": ""},
    ]


def test_normalize_recipients_from_dicts():
    raw = [{"name": "Alice", "email": "alice@x.com"}]
    out = mail_normalize.normalize_recipients(raw)
    assert out == [{"name": "Alice", "email": "alice@x.com"}]


def test_normalize_recipients_none_or_empty():
    assert mail_normalize.normalize_recipients(None) == []
    assert mail_normalize.normalize_recipients([]) == []


# ---------------------------------------------------------------------------
#  id resolution
# ---------------------------------------------------------------------------

def test_resolve_message_id_uses_internet_message_id():
    mid = mail_normalize.resolve_message_id("<abc123@mail.example.com>", "ENTRYID-XYZ")
    assert mid == "<abc123@mail.example.com>"


def test_resolve_message_id_falls_back_to_entryid_when_none():
    mid = mail_normalize.resolve_message_id(None, "ENTRYID-XYZ")
    assert mid == "entryid:ENTRYID-XYZ"


def test_resolve_message_id_falls_back_to_entryid_when_blank():
    mid = mail_normalize.resolve_message_id("   ", "ENTRYID-XYZ")
    assert mid == "entryid:ENTRYID-XYZ"


def test_resolve_message_id_strips_internet_message_id():
    mid = mail_normalize.resolve_message_id("  <abc@x.com>  ", "ENTRYID-XYZ")
    assert mid == "<abc@x.com>"


# ---------------------------------------------------------------------------
#  build_message: full field shape
# ---------------------------------------------------------------------------

def _sample_message(**overrides):
    kwargs = dict(
        message_id="<id1@x.com>",
        conversation_id="CONV-1",
        folder="inbox",
        subject="Hello",
        sender_name="Alice Smith",
        sender_email="alice@x.com",
        to=[("Bob", "bob@x.com")],
        cc=[],
        sent_at="2026-08-18T09:00:00+01:00",
        received_at="2026-08-18T09:00:05+01:00",
        body_text="Hi there",
        has_attachments=True,
    )
    kwargs.update(overrides)
    return mail_normalize.build_message(**kwargs)


def test_build_message_field_order_matches_contract():
    msg = _sample_message()
    expected = ["id", "conversation_id", "folder", "subject", "sender_name",
                "sender_email", "to", "cc", "sent_at", "received_at",
                "body_text", "has_attachments"]
    assert list(msg.keys()) == expected


def test_build_message_values():
    msg = _sample_message()
    assert msg["id"] == "<id1@x.com>"
    assert msg["conversation_id"] == "CONV-1"
    assert msg["folder"] == "inbox"
    assert msg["subject"] == "Hello"
    assert msg["sender_name"] == "Alice Smith"
    assert msg["sender_email"] == "alice@x.com"
    assert msg["to"] == [{"name": "Bob", "email": "bob@x.com"}]
    assert msg["cc"] == []
    assert msg["sent_at"] == "2026-08-18T09:00:00+01:00"
    assert msg["received_at"] == "2026-08-18T09:00:05+01:00"
    assert msg["body_text"] == "Hi there"
    assert msg["has_attachments"] is True


def test_build_message_folder_sent_allowed():
    msg = _sample_message(folder="sent")
    assert msg["folder"] == "sent"


def test_build_message_folder_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        _sample_message(folder="drafts")


def test_build_message_conversation_id_empty_becomes_null():
    msg = _sample_message(conversation_id="")
    assert msg["conversation_id"] is None
    msg2 = _sample_message(conversation_id=None)
    assert msg2["conversation_id"] is None


def test_build_message_missing_subject_sender_become_empty_string():
    msg = _sample_message(subject=None, sender_name=None, sender_email=None)
    assert msg["subject"] == ""
    assert msg["sender_name"] == ""
    assert msg["sender_email"] == ""


def test_build_message_sent_received_at_can_be_none():
    msg = _sample_message(sent_at=None, received_at=None)
    assert msg["sent_at"] is None
    assert msg["received_at"] is None


def test_build_message_body_truncated():
    msg = _sample_message(body_text="z" * 40000)
    assert len(msg["body_text"]) == 32000


def test_build_message_has_attachments_coerced_to_bool():
    msg = _sample_message(has_attachments=1)
    assert msg["has_attachments"] is True
    msg2 = _sample_message(has_attachments=0)
    assert msg2["has_attachments"] is False


# ---------------------------------------------------------------------------
#  dedupe_messages
# ---------------------------------------------------------------------------

def test_dedupe_messages_removes_duplicate_ids_keeps_first():
    a = _sample_message(message_id="dup", subject="FIRST")
    b = _sample_message(message_id="dup", subject="SECOND")
    c = _sample_message(message_id="unique", subject="THIRD")
    out = mail_normalize.dedupe_messages([a, b, c])
    assert len(out) == 2
    assert out[0]["subject"] == "FIRST"
    assert out[1]["subject"] == "THIRD"


def test_dedupe_messages_empty_list():
    assert mail_normalize.dedupe_messages([]) == []


def test_dedupe_messages_no_duplicates_preserves_order():
    a = _sample_message(message_id="a")
    b = _sample_message(message_id="b")
    out = mail_normalize.dedupe_messages([a, b])
    assert [m["id"] for m in out] == ["a", "b"]


# ---------------------------------------------------------------------------
#  build_meta
# ---------------------------------------------------------------------------

def test_build_meta_field_order_and_values():
    fixed = "2026-08-18T18:00:00Z"
    meta = mail_normalize.build_meta(
        mailbox="delegate@x.com", window_days=5, skipped=2, generated_at=fixed)
    assert list(meta.keys()) == ["generated_at", "mailbox", "window_days",
                                 "tool", "version", "skipped"]
    assert meta == {
        "generated_at": "2026-08-18T18:00:00Z",
        "mailbox": "delegate@x.com",
        "window_days": 5,
        "tool": "export_mail",
        "version": 1,
        "skipped": 2,
    }


def test_build_meta_blank_mailbox_becomes_default():
    meta = mail_normalize.build_meta(
        mailbox="", window_days=5, skipped=0, generated_at="2026-08-18T18:00:00Z")
    assert meta["mailbox"] == "default"

    meta2 = mail_normalize.build_meta(
        mailbox=None, window_days=5, skipped=0, generated_at="2026-08-18T18:00:00Z")
    assert meta2["mailbox"] == "default"


def test_build_meta_generated_at_formats_aware_datetime_as_utc():
    dt = datetime(2026, 8, 18, 19, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    meta = mail_normalize.build_meta(mailbox="x", window_days=5, skipped=0,
                                     generated_at=dt)
    assert meta["generated_at"] == "2026-08-18T18:00:00Z"


def test_build_meta_defaults_generated_at_to_now():
    before = datetime.now(timezone.utc)
    meta = mail_normalize.build_meta(mailbox="x", window_days=5, skipped=0)
    after = datetime.now(timezone.utc)
    parsed = datetime.strptime(meta["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    assert before - timedelta(seconds=2) <= parsed <= after + timedelta(seconds=2)


# ---------------------------------------------------------------------------
#  build_output: full document shape (pins the whole frozen contract)
# ---------------------------------------------------------------------------

def test_build_output_full_shape():
    msg1 = _sample_message(message_id="m1", folder="inbox")
    msg2 = _sample_message(message_id="m2", folder="sent")
    doc = mail_normalize.build_output(
        mailbox="delegate@x.com", window_days=5, skipped=1,
        messages=[msg1, msg2], generated_at="2026-08-18T18:00:00Z")

    assert list(doc.keys()) == ["meta", "messages"]
    assert doc["meta"] == {
        "generated_at": "2026-08-18T18:00:00Z",
        "mailbox": "delegate@x.com",
        "window_days": 5,
        "tool": "export_mail",
        "version": 1,
        "skipped": 1,
    }
    assert len(doc["messages"]) == 2
    assert doc["messages"][0]["id"] == "m1"
    assert doc["messages"][1]["id"] == "m2"


def test_build_output_dedupes_messages():
    msg1 = _sample_message(message_id="dup")
    msg2 = _sample_message(message_id="dup")
    doc = mail_normalize.build_output(
        mailbox="", window_days=5, skipped=0, messages=[msg1, msg2],
        generated_at="2026-08-18T18:00:00Z")
    assert len(doc["messages"]) == 1


def test_build_output_empty_messages():
    doc = mail_normalize.build_output(
        mailbox="", window_days=5, skipped=0, messages=[],
        generated_at="2026-08-18T18:00:00Z")
    assert doc["messages"] == []
    assert doc["meta"]["mailbox"] == "default"


def test_build_output_is_json_serializable():
    import json
    msg = _sample_message(message_id="m1")
    doc = mail_normalize.build_output(
        mailbox="x", window_days=5, skipped=0, messages=[msg],
        generated_at="2026-08-18T18:00:00Z")
    # Round-trips cleanly and preserves key order for the top level + message.
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    reparsed = json.loads(text)
    assert reparsed == doc
