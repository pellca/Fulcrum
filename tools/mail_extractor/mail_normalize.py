"""Pure mail normalization logic (no COM, no file IO, stdlib only).

This module is the mail-extractor analogue of OutlookDiaryExtractor's
diary_merge.py: everything here is a pure function operating on plain scalars
and dicts, so it imports and unit-tests cleanly on any platform (Linux,
macOS, Windows), Python 3.8+. The COM harvest layer (export_mail.py) reads
Outlook properties and hands them to build_message()/build_output() -- it
never builds the output dict itself.

Output contract (FROZEN -- the Fulcrum backend importer is built against this
shape in parallel; do not change field names, nesting or the meta block
without updating that importer too):

    {
      "meta": {
        "generated_at": "<ISO-8601 UTC, ...Z>",
        "mailbox": "<name or 'default'>",
        "window_days": <int>,
        "tool": "export_mail",
        "version": 1,
        "skipped": <int>
      },
      "messages": [ {
          "id": "<internet-message-id or entryid:...>",
          "conversation_id": "<str or null>",
          "folder": "inbox" | "sent",
          "subject": "<str>",
          "sender_name": "<str>", "sender_email": "<smtp or ''>",
          "to": [{"name": "...", "email": "..."}], "cc": [...],
          "sent_at": "<ISO or null>", "received_at": "<ISO or null>",
          "body_text": "<str, <=32000 chars>",
          "has_attachments": true|false
      } ]
    }
"""

from datetime import datetime, timezone


BODY_MAX_CHARS = 32000
TOOL_NAME = "export_mail"
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
#  Formatting helpers
# ---------------------------------------------------------------------------

def iso_utc(dt):
    """UTC ISO-8601 with a trailing Z, e.g. 2026-08-18T12:00:00Z.

    Naive datetimes are assumed to already be UTC (the COM layer always
    passes aware datetimes). Mirrors diary_merge.iso_utc.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_local_offset(dt):
    """Local-offset ISO-8601, e.g. 2026-08-18T14:00:00+01:00, or None.

    Used for sent_at / received_at, matching the diary tool's datetime
    formatting for local-offset fields (start/end). Python's %z does not
    render the colon in the offset, so it is built by hand from
    utcoffset(). Returns None when dt is None (message never sent/received
    on that axis, e.g. a draft has no SentOn).
    """
    if dt is None:
        return None
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    off = dt.utcoffset()
    if off is None:
        # Should not happen on the real path (COM datetimes are aware); treat
        # as UTC to stay well-defined rather than crashing.
        return base + "+00:00"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours = total // 3600
    minutes = (total % 3600) // 60
    return "%s%s%02d:%02d" % (base, sign, hours, minutes)


def truncate_body(text):
    """Coerce to str and cap at BODY_MAX_CHARS. None -> ''."""
    if text is None:
        return ""
    text = str(text)
    if len(text) > BODY_MAX_CHARS:
        return text[:BODY_MAX_CHARS]
    return text


# ---------------------------------------------------------------------------
#  Recipients
# ---------------------------------------------------------------------------

def normalize_recipient(name, email):
    """Shape one recipient as {"name": ..., "email": ...}; None -> ''."""
    return {"name": name or "", "email": email or ""}


def normalize_recipients(raw_list):
    """Normalize a list of recipients to [{"name", "email"}, ...].

    Accepts an iterable of either (name, email) tuples or dicts already
    holding "name"/"email" keys, so the COM layer can pass either shape.
    None / empty -> [].
    """
    out = []
    if not raw_list:
        return out
    for item in raw_list:
        if isinstance(item, dict):
            name = item.get("name")
            email = item.get("email")
        else:
            name, email = item
        out.append(normalize_recipient(name, email))
    return out


# ---------------------------------------------------------------------------
#  Id resolution
# ---------------------------------------------------------------------------

def resolve_message_id(internet_message_id, entry_id):
    """Stable message id: PR_INTERNET_MESSAGE_ID if present, else
    "entryid:" + EntryID.

    A blank/whitespace-only internet_message_id is treated as absent (some
    internal/rerouted mail leaves it empty rather than missing).
    """
    if internet_message_id:
        stripped = str(internet_message_id).strip()
        if stripped:
            return stripped
    return "entryid:" + str(entry_id)


# ---------------------------------------------------------------------------
#  Message builder
# ---------------------------------------------------------------------------

def build_message(message_id, conversation_id, folder, subject, sender_name,
                  sender_email, to, cc, sent_at, received_at, body_text,
                  has_attachments):
    """Build one normalized message dict matching the frozen output contract.

    PURE: callers (the COM layer) read Outlook properties and pass plain
    values in. sent_at / received_at are expected to already be ISO strings
    (or None) -- format them with iso_local_offset() before calling.

    The returned dict's key order matches the contract exactly (Python
    dicts preserve insertion order, and json.dump serializes in that order).
    """
    if folder not in ("inbox", "sent"):
        raise ValueError("folder must be 'inbox' or 'sent', got %r" % (folder,))

    return {
        "id": message_id,
        "conversation_id": conversation_id if conversation_id else None,
        "folder": folder,
        "subject": subject or "",
        "sender_name": sender_name or "",
        "sender_email": sender_email or "",
        "to": normalize_recipients(to),
        "cc": normalize_recipients(cc),
        "sent_at": sent_at,
        "received_at": received_at,
        "body_text": truncate_body(body_text),
        "has_attachments": bool(has_attachments),
    }


# ---------------------------------------------------------------------------
#  De-duplication
# ---------------------------------------------------------------------------

def dedupe_messages(messages):
    """De-duplicate a message list by id, keeping the FIRST occurrence and
    preserving order (a message can appear once per run)."""
    seen = set()
    out = []
    for m in messages:
        mid = m.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        out.append(m)
    return out


# ---------------------------------------------------------------------------
#  meta / full-document assembly
# ---------------------------------------------------------------------------

def build_meta(mailbox, window_days, skipped, generated_at=None):
    """Build the meta block. generated_at: an aware datetime (default: now)
    or an already-formatted ISO string (tests can pin a fixed value)."""
    if generated_at is None:
        generated_at = datetime.now().astimezone()
    if hasattr(generated_at, "strftime"):
        generated_at_iso = iso_utc(generated_at)
    else:
        generated_at_iso = generated_at

    return {
        "generated_at": generated_at_iso,
        "mailbox": mailbox if mailbox else "default",
        "window_days": window_days,
        "tool": TOOL_NAME,
        "version": SCHEMA_VERSION,
        "skipped": skipped,
    }


def build_output(mailbox, window_days, skipped, messages, generated_at=None):
    """Build the full mailbox.json document: meta + de-duplicated messages.

    PURE and total: given the harvested (already-normalized) message dicts,
    this is the single place that assembles the frozen top-level shape, so
    a shape test against this function pins the whole contract.
    """
    return {
        "meta": build_meta(mailbox, window_days, skipped, generated_at),
        "messages": dedupe_messages(messages),
    }
