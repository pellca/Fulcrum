#!/usr/bin/env python3
"""Export the last N days of Outlook Inbox + Sent Items to mailbox.json via
desktop Outlook COM automation.

Sibling tool to /home/cp/Dev/OutlookDiaryExtractor/export_diary.py, same
rationale: the corporate target machine runs PowerShell in Constrained
Language Mode, which blocks `New-Object -ComObject`. CLM does not constrain
Python, so pywin32 COM automation through Python is the only viable host.

ALL pure logic (normalizing raw per-message values into the output schema,
truncation, id fallback, recipient shaping, the meta block, dedup) lives in
mail_normalize.py, which is stdlib-only and imports on any OS. This module is
the thin harvest + IO layer: it never builds the output dict itself, it only
reads Outlook COM properties and json-serializes what mail_normalize.py hands
back. pywin32 is imported lazily INSIDE _attach_to_outlook, so this module
still imports fine on Linux for testing/CLI-parsing checks
(`python3 -c "import export_mail"`).

Target: Python 3.8+ (no match statements, no runtime X | Y annotations).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import mail_normalize


# MAPI property tags used via PropertyAccessor.GetProperty(). Each is a MAPI
# named/standard property addressed by its proptag URI; see the per-fallback
# comments below for why each one is read this way rather than via the plain
# COM property.
PR_SENDER_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"
PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"

OL_MAIL_ITEM_CLASS = 43  # olMail: MailItem.Class value; guards against
                         # non-mail items (meeting requests, receipts, etc.)
                         # turning up in Inbox/Sent Items.
OL_TO = 1   # olTo   -- Recipient.Type for a To recipient
OL_CC = 2   # olCC   -- Recipient.Type for a Cc recipient

FOLDER_NAMES = {"inbox": "Inbox", "sent": "Sent Items"}
DEFAULT_FOLDER_IDS = {"inbox": 6, "sent": 5}  # olFolderInbox, olFolderSentMail


# ============================================================================
#  Restrict date formatting (Windows-only code path, but pure enough to test)
# ============================================================================

def format_restrict_datetime(dt):
    """Format a datetime for an Items.Restrict() filter literal.

    THE CLASSIC RESTRICT GOTCHA: Outlook's Items.Restrict() parses date/time
    literals in the filter STRING itself, not via a typed argument, and it
    expects them in US short-date + 12-hour-clock form: %m/%d/%Y %I:%M %p
    (e.g. "08/13/2026 09:00 AM"). Passing an ISO string, a 24-hour time, or a
    non-US day/month order here does not raise -- it silently matches zero
    items or the wrong window. (The sibling OutlookDiaryExtractor tool goes
    further and asks Windows for the *locale* short-date format via
    GetDateFormatW/GetTimeFormatW for full locale safety; this tool instead
    hard-codes the fixed %m/%d/%Y %I:%M %p pattern, which is what Restrict()
    itself expects for its literal regardless of the machine's regional
    settings.)
    """
    return dt.strftime("%m/%d/%Y %I:%M %p")


# ============================================================================
#  COM layer -- only ever reached from run_export (real run path)
# ============================================================================

def _ensure_aware(dt):
    """Re-anchor a pywin32 COM datetime to its correct local offset.

    pywin32/pywintypes datetimes are NOT naive and NOT honestly aware: they
    come back with tzinfo already attached, but that tzinfo is a fixed
    zero/UTC offset while the wall-clock fields (year/month/.../hour/minute)
    are already local time. So `dt.tzinfo is None` never fires and a naive
    check does nothing -- the mislabelled value passes straight through, and
    downstream ISO formatting faithfully renders local wall clock stamped
    "+00:00". In UK summer (BST) every timestamp ends up an hour off as an
    instant, even though it prints something that looks plausible.

    The fix is to DISCARD the COM tzinfo and let the platform re-derive the
    offset from the wall-clock fields: strip tzinfo to get a naive datetime
    holding the (correct) local wall clock, then call .astimezone(), which
    for a naive input interprets it as local time and attaches the right
    offset for that specific date -- so DST is resolved per-date rather than
    inherited from whatever (wrong) offset COM handed us. Mirrors
    OutlookDiaryExtractor's export_diary._ensure_aware.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=None).astimezone()


def _attach_to_outlook():
    """Attach to the already-running desktop Outlook, preferring early
    binding. See export_diary.py's _attach_to_outlook for the full early- vs
    late-binding rationale; behaviour here is identical. We NEVER call
    .Quit() on the returned application.
    """
    import win32com.client  # noqa: import here so the module loads on Linux

    try:
        from win32com.client import gencache
        return gencache.EnsureDispatch("Outlook.Application")
    except Exception:  # noqa: BLE001 - unwritable/stale gen_py, policy, etc.
        return win32com.client.Dispatch("Outlook.Application")


def _resolve_folder(ns, mailbox_name, folder_kind):
    """Resolve the Inbox/Sent Items folder for the given mailbox.

    folder_kind: "inbox" or "sent". When mailbox_name is set, look it up
    among the top-level stores in ns.Folders (each store's .Name is the
    mailbox/display name as it appears in Outlook's folder list -- this is
    how a delegate/shared mailbox that has been added to the profile shows
    up) and take its Inbox/Sent Items subfolder. Falls back to
    GetDefaultFolder() -- the signed-in user's own mailbox -- when
    mailbox_name is blank, or when the named store/subfolder cannot be
    found (e.g. a shared mailbox added via "Open Shared Mailbox" rather than
    as a full extra account, which may not always expose a Sent Items of its
    own).
    """
    default_id = DEFAULT_FOLDER_IDS[folder_kind]
    subfolder_name = FOLDER_NAMES[folder_kind]

    if mailbox_name:
        store_root = None
        try:
            for i in range(1, ns.Folders.Count + 1):
                candidate = ns.Folders.Item(i)
                try:
                    if candidate.Name == mailbox_name:
                        store_root = candidate
                        break
                except Exception:  # noqa: BLE001 - unreadable store, skip it
                    continue
        except Exception:  # noqa: BLE001
            store_root = None

        if store_root is not None:
            try:
                return store_root.Folders.Item(subfolder_name)
            except Exception:  # noqa: BLE001 - fall through to default folder
                pass

    return ns.GetDefaultFolder(default_id)


def _get_property_safe(obj, tag):
    """PropertyAccessor.GetProperty(tag), or None on any failure (missing
    property, access denied, unsupported item type, ...)."""
    try:
        return obj.PropertyAccessor.GetProperty(tag)
    except Exception:  # noqa: BLE001
        return None


def _resolve_via_gal(ns, ex_address):
    """Resolve a legacy Exchange X.500 DN to SMTP through the GAL:
    ns.CreateRecipient(dn).Resolve() -> AddressEntry.GetExchangeUser()
    .PrimarySmtpAddress. Needed because PR_SENDER_SMTP_ADDRESS /
    PR_SMTP_ADDRESS come back EMPTY (not an error) on EX-typed entries with
    no cached SMTP proxy — observed in pre-flight on this tenant."""
    if ns is None or not ex_address:
        return ""
    try:
        rcpt = ns.CreateRecipient(ex_address)
        if rcpt.Resolve():
            exch_user = rcpt.AddressEntry.GetExchangeUser()
            if exch_user is not None:
                return exch_user.PrimarySmtpAddress or ""
    except Exception:  # noqa: BLE001
        pass
    return ""


def _resolve_sender_email(item, ns=None):
    """Resolve the sender's SMTP address with four guarded fallback steps,
    in priority order:

      1. PR_SENDER_SMTP_ADDRESS via PropertyAccessor -- works for both
         Exchange and non-Exchange senders and is the most reliable single
         source, but returns EMPTY (no exception) on EX-typed senders with
         no cached SMTP proxy.
      2. SenderEmailAddress, but ONLY when SenderEmailType == "SMTP" -- for
         Exchange-typed senders SenderEmailAddress is a legacy X.500 DN, not
         an SMTP address, so it is unusable unless the type says SMTP.
      3. Sender.GetExchangeUser().PrimarySmtpAddress -- resolves the
         Exchange DN to SMTP via the GAL when the AddressEntry is directly
         reachable from the item.
      4. ns.CreateRecipient(<EX DN>).Resolve() -> GAL -- the namespace-side
         resolution, which works even when step 3's item-side AddressEntry
         path yields nothing (pre-flight confirmed this on this tenant).

    Each step is independently guarded: a failure at any step falls through
    to the next rather than aborting extraction of the message.
    """
    smtp = _get_property_safe(item, PR_SENDER_SMTP_ADDRESS)
    if smtp:
        return smtp

    try:
        if getattr(item, "SenderEmailType", None) == "SMTP":
            addr = item.SenderEmailAddress
            if addr:
                return addr
    except Exception:  # noqa: BLE001
        pass

    try:
        sender = item.Sender
        if sender is not None:
            exch_user = sender.GetExchangeUser()
            if exch_user is not None:
                addr = exch_user.PrimarySmtpAddress
                if addr:
                    return addr
    except Exception:  # noqa: BLE001
        pass

    try:
        if getattr(item, "SenderEmailType", None) == "EX":
            addr = _resolve_via_gal(ns, item.SenderEmailAddress)
            if addr:
                return addr
    except Exception:  # noqa: BLE001
        pass

    return ""


def _resolve_recipient_email(recipient, ns=None):
    """Resolve one Recipient's SMTP address: PR_SMTP_ADDRESS via
    PropertyAccessor first (may be EMPTY, not an error, on EX entries with no
    cached SMTP proxy), then AddressEntry GAL resolution, then namespace-side
    CreateRecipient/Resolve on the recipient's address, and finally the
    AddressEntry's own .Address -- but only when it looks like SMTP, so a
    legacy X.500 DN never lands in the email field. Each step guarded;
    '' if nothing resolves."""
    smtp = _get_property_safe(recipient, PR_SMTP_ADDRESS)
    if smtp:
        return smtp

    try:
        addr_entry = recipient.AddressEntry
    except Exception:  # noqa: BLE001
        addr_entry = None

    if addr_entry is not None:
        try:
            exch_user = addr_entry.GetExchangeUser()
            if exch_user is not None:
                addr = exch_user.PrimarySmtpAddress
                if addr:
                    return addr
        except Exception:  # noqa: BLE001
            pass

    try:
        addr = _resolve_via_gal(ns, getattr(recipient, "Address", None))
        if addr:
            return addr
    except Exception:  # noqa: BLE001
        pass

    if addr_entry is not None:
        try:
            addr = addr_entry.Address
            if addr and "@" in addr and not addr.startswith("/"):
                return addr
        except Exception:  # noqa: BLE001
            pass

    return ""


def _harvest_recipients(item, recipient_type, ns=None):
    """Collect To/Cc recipients (recipient_type: OL_TO or OL_CC) as
    (name, email) tuples. A failure reading one recipient is skipped rather
    than aborting the whole message (mail_normalize.normalize_recipients
    does the final {"name","email"} shaping)."""
    out = []
    try:
        recipients = item.Recipients
        count = recipients.Count
    except Exception:  # noqa: BLE001
        return out

    for i in range(1, count + 1):
        try:
            r = recipients.Item(i)
        except Exception:  # noqa: BLE001
            continue
        try:
            if r.Type != recipient_type:
                continue
        except Exception:  # noqa: BLE001
            continue
        try:
            name = r.Name or ""
        except Exception:  # noqa: BLE001
            name = ""
        email = _resolve_recipient_email(r, ns)
        out.append((name, email))

    return out


def _resolve_message_id(item):
    """PR_INTERNET_MESSAGE_ID via PropertyAccessor, falling back to
    "entryid:" + EntryID (mail_normalize.resolve_message_id owns the actual
    fallback rule; this just reads the two raw COM values)."""
    internet_id = _get_property_safe(item, PR_INTERNET_MESSAGE_ID)
    try:
        entry_id = item.EntryID
    except Exception:  # noqa: BLE001
        entry_id = ""
    return mail_normalize.resolve_message_id(internet_id, entry_id)


def _extract_message(item, folder_label, ns=None):
    """Read one MailItem's properties and hand them to
    mail_normalize.build_message(). Returns the normalized dict, or None if
    this item is not a MailItem (caller still counts that as a skip)."""
    try:
        if item.Class != OL_MAIL_ITEM_CLASS:
            return None
    except Exception:  # noqa: BLE001
        return None

    try:
        subject = item.Subject or ""
    except Exception:  # noqa: BLE001
        subject = ""

    try:
        sender_name = item.SenderName or ""
    except Exception:  # noqa: BLE001
        sender_name = ""

    sender_email = _resolve_sender_email(item, ns)
    to = _harvest_recipients(item, OL_TO, ns)
    cc = _harvest_recipients(item, OL_CC, ns)

    try:
        sent_at = mail_normalize.iso_local_offset(_ensure_aware(item.SentOn))
    except Exception:  # noqa: BLE001
        sent_at = None

    try:
        received_at = mail_normalize.iso_local_offset(_ensure_aware(item.ReceivedTime))
    except Exception:  # noqa: BLE001
        received_at = None

    try:
        body_text = item.Body or ""
    except Exception:  # noqa: BLE001
        body_text = ""

    try:
        has_attachments = item.Attachments.Count > 0
    except Exception:  # noqa: BLE001
        has_attachments = False

    try:
        conversation_id = item.ConversationID or None
    except Exception:  # noqa: BLE001
        conversation_id = None

    message_id = _resolve_message_id(item)

    return mail_normalize.build_message(
        message_id=message_id,
        conversation_id=conversation_id,
        folder=folder_label,
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email,
        to=to,
        cc=cc,
        sent_at=sent_at,
        received_at=received_at,
        body_text=body_text,
        has_attachments=has_attachments)


def _harvest_folder(folder, folder_label, window_from, ns=None):
    """Restrict `folder` to [window_from, now) and extract every MailItem.

    Restrict filters on ReceivedTime for both folders (Sent Items sets
    ReceivedTime too -- Outlook stamps it when the item lands in the folder,
    which for a sent message is effectively send time -- so one filter
    property covers both without a folder-specific branch).

    Every item is wrapped in its own try/except: one corrupt/unreadable item
    (a stub, a permissions hiccup, a malformed MAPI object) must never kill
    the run. item.Class != MailItem (e.g. a meeting request or read receipt
    sitting in the same folder) is also counted as a skip, not an error.

    Returns (messages, skipped_count).
    """
    filter_str = "[ReceivedTime] >= '%s'" % format_restrict_datetime(window_from)
    restricted = folder.Items.Restrict(filter_str)

    messages = []
    skipped = 0

    for item in restricted:
        try:
            msg = _extract_message(item, folder_label, ns)
        except Exception:  # noqa: BLE001 - never let one bad item kill the run
            skipped += 1
            continue
        if msg is None:
            skipped += 1
            continue
        messages.append(msg)

    return messages, skipped


# ============================================================================
#  Orchestration (real run path)
# ============================================================================

def run_export(mailbox, days, out_file):
    """The real run path -- the only function that reaches COM."""
    start_time = time.monotonic()

    # Resolve to an absolute path once: relative paths resolve against the
    # process CWD, which can differ under Task Scheduler.
    out_file = os.path.abspath(out_file)

    window_from = datetime.now().astimezone() - timedelta(days=days)

    print("Mail window: last %d day(s) (since %s)  (mailbox: %s)" % (
        days, window_from.strftime("%Y-%m-%d %H:%M"), mailbox or "default"))

    try:
        outlook = _attach_to_outlook()
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(
            "Could not attach to Outlook. Ensure the desktop Outlook client "
            "is running. Underlying error: %s" % ex)

    ns = outlook.GetNamespace("MAPI")

    inbox_folder = _resolve_folder(ns, mailbox, "inbox")
    sent_folder = _resolve_folder(ns, mailbox, "sent")

    inbox_messages, inbox_skipped = _harvest_folder(inbox_folder, "inbox", window_from, ns)
    sent_messages, sent_skipped = _harvest_folder(sent_folder, "sent", window_from, ns)

    all_messages = inbox_messages + sent_messages
    skipped_total = inbox_skipped + sent_skipped

    doc = mail_normalize.build_output(
        mailbox=mailbox, window_days=days, skipped=skipped_total,
        messages=all_messages)

    write_mailbox_file(out_file, doc)

    elapsed = round(time.monotonic() - start_time, 2)

    print("")
    print("Mailbox export written to %s" % out_file)
    print("  inbox:     %d" % len(inbox_messages))
    print("  sent:      %d" % len(sent_messages))
    print("  total:     %d" % len(doc["messages"]))
    print("  skipped:   %d" % skipped_total)
    print("  elapsed:   %ss" % elapsed)


def write_mailbox_file(path, doc):
    """Write the full mailbox.json document atomically as UTF-8 (no BOM).

    Every run rewrites the full current window in one shot (no incremental
    merge file -- the Fulcrum importer upserts idempotently by id), so this
    is a plain atomic replace: write a temp file in the same directory, then
    os.replace over the target. Mirrors export_diary.py's write_diary_file.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ============================================================================
#  CLI
# ============================================================================

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="export_mail.py",
        description="Export the last N days of Outlook Inbox + Sent Items to "
                    "mailbox.json via desktop Outlook COM.")
    parser.add_argument("--days", type=int, default=5,
                        help="Number of days back from now to include (default 5).")
    parser.add_argument("--out", default="./mailbox.json",
                        help="Output JSON path (written atomically; dir auto-created).")
    parser.add_argument("--mailbox", default="",
                        help="Delegate/shared mailbox display name to read "
                             "(optional). Default: the signed-in user's own "
                             "mailbox.")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.days <= 0:
        sys.stderr.write("ERROR: --days must be a positive integer.\n")
        return 2

    try:
        run_export(mailbox=args.mailbox, days=args.days, out_file=args.out)
    except Exception as ex:  # noqa: BLE001 - surface a friendly message + exit 1
        sys.stderr.write("ERROR: %s\n" % ex)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
