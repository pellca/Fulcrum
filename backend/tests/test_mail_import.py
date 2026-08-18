"""Import a mailbox.json produced by the mail extractor (tools/mail_extractor).

The extractor guarantees: each file is the FULL current window (no deltas), so
import is an idempotent upsert by message `id`. Content fields are refreshed on
every import; `triage`/`triaged_at` are user state and are always preserved.
"""

import json
from datetime import date, timedelta

from app.config import MAIL_RETENTION_DAYS
from app.db import SessionLocal
from app.models import Link, MailMessage, Person, PersonAlias
from app.services.mail_import import import_mailbox, resolve_email

TODAY = date.today()


def _mailbox(messages, version=1, **meta_overrides):
    meta = {
        "generated_at": f"{TODAY.isoformat()}T09:00:00Z",
        "mailbox": "delegate@bank.com",
        "window_days": 5,
        "tool": "export_mail",
        "version": version,
        "skipped": 0,
    }
    meta.update(meta_overrides)
    return {"meta": meta, "messages": messages}


def _msg(
    msg_id,
    folder="inbox",
    subject="Subject",
    body="Body text",
    sender_name="Alex Morgan",
    sender_email="alex.morgan@bank.com",
    to=None,
    cc=None,
    sent_at=None,
    received_at=None,
    has_attachments=False,
    conversation_id=None,
):
    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "folder": folder,
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to": to or [],
        "cc": cc or [],
        "sent_at": sent_at,
        "received_at": received_at,
        "body_text": body,
        "has_attachments": has_attachments,
    }


def _row(db, message_id):
    """Look up a MailMessage by the extractor's stable message_id (not the
    surrogate integer PK)."""
    return db.query(MailMessage).filter(MailMessage.message_id == message_id).first()


# ---------- service-level: upsert, occurred_date, retention, resolve_email ----------


def test_import_is_idempotent_upsert(db):
    msg = _msg("m1", received_at=f"{TODAY.isoformat()}T09:00:00Z", subject="First subject")
    summary = import_mailbox(db, _mailbox([msg]))
    assert summary == {"added": 1, "updated": 0, "purged": 0}
    assert db.query(MailMessage).count() == 1

    summary2 = import_mailbox(db, _mailbox([msg]))
    assert summary2["added"] == 0
    assert summary2["updated"] == 1
    assert db.query(MailMessage).count() == 1

    # the surrogate PK is stable across re-import (upsert keyed on message_id)
    row = _row(db, "m1")
    row_id = row.id
    import_mailbox(db, _mailbox([msg]))
    assert _row(db, "m1").id == row_id


def test_triage_preserved_content_refreshed_on_reimport(db):
    msg = _msg(
        "m1", received_at=f"{TODAY.isoformat()}T09:00:00Z", subject="Original subject", body="Original body"
    )
    import_mailbox(db, _mailbox([msg]))

    row = _row(db, "m1")
    row.triage = "linked"
    row.triaged_at = "2026-08-10T12:00:00"
    db.commit()

    updated = _msg(
        "m1", received_at=f"{TODAY.isoformat()}T09:00:00Z", subject="Updated subject", body="Updated body"
    )
    summary = import_mailbox(db, _mailbox([updated]))
    assert summary["added"] == 0 and summary["updated"] == 1

    row = _row(db, "m1")
    assert row.subject == "Updated subject"
    assert row.body_text == "Updated body"
    assert row.triage == "linked"
    assert row.triaged_at == "2026-08-10T12:00:00"


def test_occurred_date_derivation(db):
    # relative to today so the rows stay inside the retention window whenever this runs
    d1 = (TODAY - timedelta(days=1)).isoformat()
    d2 = (TODAY - timedelta(days=2)).isoformat()
    d3 = (TODAY - timedelta(days=3)).isoformat()
    d4 = (TODAY - timedelta(days=4)).isoformat()

    messages = [
        _msg("inbox-primary", folder="inbox", received_at=f"{d1}T09:00:00Z", sent_at=None),
        _msg("sent-primary", folder="sent", sent_at=f"{d2}T09:00:00Z", received_at=None),
        _msg("inbox-fallback", folder="inbox", received_at=None, sent_at=f"{d3}T09:00:00Z"),
        _msg("sent-fallback", folder="sent", sent_at=None, received_at=f"{d4}T09:00:00Z"),
        _msg("no-dates", folder="inbox", received_at=None, sent_at=None),
    ]
    summary = import_mailbox(db, _mailbox(messages))

    assert _row(db, "inbox-primary").occurred_date == d1
    assert _row(db, "sent-primary").occurred_date == d2
    assert _row(db, "inbox-fallback").occurred_date == d3
    assert _row(db, "sent-fallback").occurred_date == d4
    # a message with neither date can never match the day window, so it would be
    # invisible forever: it is purged in the same run rather than kept as a ghost
    assert _row(db, "no-dates") is None
    assert summary["purged"] == 1


def test_retention_purge_respects_triage_and_links(db):
    old_date = (TODAY - timedelta(days=MAIL_RETENTION_DAYS + 10)).isoformat()
    recent_date = (TODAY - timedelta(days=1)).isoformat()

    old_ref = MailMessage(
        message_id="old_ref", folder="inbox", occurred_date=old_date,
        received_at=f"{old_date}T09:00:00Z", subject="old referenced", triage="dismissed",
    )
    db.add_all(
        [
            MailMessage(
                message_id="old_pending", folder="inbox", occurred_date=old_date,
                received_at=f"{old_date}T09:00:00Z", subject="old pending", triage="pending",
            ),
            MailMessage(
                message_id="old_linked", folder="inbox", occurred_date=old_date,
                received_at=f"{old_date}T09:00:00Z", subject="old linked", triage="linked",
            ),
            old_ref,
            MailMessage(
                message_id="recent_msg", folder="inbox", occurred_date=recent_date,
                received_at=f"{recent_date}T09:00:00Z", subject="recent", triage="pending",
            ),
        ]
    )
    db.flush()  # populate old_ref.id (autoincrement PK) before the Link references it
    db.add(Link(from_type="mail", from_id=old_ref.id, to_type="action", to_id=1, kind="relates"))
    db.commit()

    summary = import_mailbox(db, _mailbox([]))
    assert summary["purged"] == 1

    remaining = {row.message_id for row in db.query(MailMessage).all()}
    assert remaining == {"old_linked", "old_ref", "recent_msg"}


def test_retention_boundary_and_link_direction(db):
    exact = (TODAY - timedelta(days=MAIL_RETENTION_DAYS)).isoformat()  # kept
    over = (TODAY - timedelta(days=MAIL_RETENTION_DAYS + 1)).isoformat()  # purged

    link_target = MailMessage(message_id="link_target", folder="inbox", occurred_date=over, triage="pending")
    db.add_all(
        [
            MailMessage(message_id="exact_boundary", folder="inbox", occurred_date=exact, triage="pending"),
            MailMessage(message_id="one_day_over", folder="inbox", occurred_date=over, triage="pending"),
            link_target,
        ]
    )
    db.flush()  # populate link_target.id before the Link references it
    # the Link check must look at to_type as well as from_type
    db.add(Link(from_type="action", from_id=1, to_type="mail", to_id=link_target.id, kind="relates"))
    db.commit()

    summary = import_mailbox(db, _mailbox([]))
    assert summary["purged"] == 1
    assert {row.message_id for row in db.query(MailMessage).all()} == {"exact_boundary", "link_target"}


def test_folder_change_between_runs_reshapes_occurred_date(db):
    sent_day = (TODAY - timedelta(days=2)).isoformat()
    received_day = TODAY.isoformat()
    inbox_copy = _msg(
        "moved", folder="inbox", sent_at=f"{sent_day}T08:00:00Z", received_at=f"{received_day}T09:00:00Z"
    )
    import_mailbox(db, _mailbox([inbox_copy]))
    assert _row(db, "moved").occurred_date == received_day

    sent_copy = dict(inbox_copy, folder="sent")
    summary = import_mailbox(db, _mailbox([sent_copy]))
    assert summary["added"] == 0 and summary["updated"] == 1
    row = _row(db, "moved")
    assert row.folder == "sent"
    assert row.occurred_date == sent_day  # re-derived from the new folder


def test_resolve_email_matches_person_and_alias(db):
    person = Person(name="Sarah Chen", email="Sarah.Chen@Bank.com")
    db.add(person)
    db.flush()
    db.add(PersonAlias(alias="s.chen@partner.example", person_id=person.id))
    db.commit()

    assert resolve_email(db, "sarah.chen@bank.com").id == person.id
    assert resolve_email(db, "S.CHEN@PARTNER.EXAMPLE").id == person.id
    assert resolve_email(db, "nobody@bank.com") is None
    assert resolve_email(db, None) is None
    assert resolve_email(db, "") is None


def test_rejects_malformed_mailbox(db):
    try:
        import_mailbox(db, {"foo": 1})
        raise AssertionError("should have raised")
    except ValueError as exc:
        assert "messages" in str(exc)

    try:
        import_mailbox(db, _mailbox([], version=2))
        raise AssertionError("should have raised")
    except ValueError as exc:
        assert "version" in str(exc).lower()

    # wrong types must surface as ValueError (-> 422), not an AttributeError 500
    for payload in ({"messages": {"m1": {}}}, {"messages": ["not-an-object"]}):
        try:
            import_mailbox(db, payload)
            raise AssertionError("should have raised")
        except ValueError:
            pass
    # a non-dict meta is tolerated rather than fatal (version check simply skipped)
    assert import_mailbox(db, {"meta": "nonsense", "messages": []})["added"] == 0


# ---------- API-level: import endpoints, GET filters, stats, clear, links ----------


def test_import_via_path_and_upload_endpoints(client, tmp_path):
    msg = _msg("m1", received_at=f"{TODAY.isoformat()}T09:00:00Z")
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox([msg])), encoding="utf-8")

    result = client.post("/api/mail/import", json={"path": str(path)}).json()
    assert result == {"added": 1, "updated": 0, "purged": 0}

    assert client.post("/api/mail/import", json={"path": "/no/such/file.json"}).status_code == 404

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    assert client.post("/api/mail/import", json={"path": str(bad_path)}).status_code == 422

    msg2 = _msg("m2", received_at=f"{TODAY.isoformat()}T09:00:00Z")
    upload = client.post(
        "/api/mail/import-upload",
        files={"file": ("mailbox.json", json.dumps(_mailbox([msg2])), "application/json")},
    ).json()
    assert upload == {"added": 1, "updated": 0, "purged": 0}

    bad_upload = client.post(
        "/api/mail/import-upload",
        files={"file": ("bad.json", json.dumps({"foo": 1}), "application/json")},
    )
    assert bad_upload.status_code == 422


def test_get_messages_filters_and_ordering(client, tmp_path):
    day0 = TODAY.isoformat()
    day4 = (TODAY - timedelta(days=4)).isoformat()  # inside the default 5-day window boundary
    day5 = (TODAY - timedelta(days=5)).isoformat()  # just outside it

    messages = [
        _msg("boundary_in", received_at=f"{day4}T08:00:00Z", subject="Boundary in"),
        _msg("boundary_out", received_at=f"{day5}T08:00:00Z", subject="Boundary out"),
        _msg("today_inbox_early", received_at=f"{day0}T08:00:00Z", subject="Today inbox early", folder="inbox"),
        _msg("today_inbox_late", received_at=f"{day0}T09:00:00Z", subject="Today inbox late", folder="inbox"),
        _msg("today_sent", sent_at=f"{day0}T10:00:00Z", subject="Today sent", folder="sent"),
    ]
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox(messages)), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    default_days = client.get("/api/mail/messages").json()  # default days=5
    # each row now carries both the surrogate int id and the extractor's message_id
    assert all(isinstance(m["id"], int) for m in default_days)
    assert {m["message_id"] for m in default_days} == {
        "boundary_in", "today_inbox_early", "today_inbox_late", "today_sent"
    }
    assert "boundary_out" not in {m["message_id"] for m in default_days}

    # newest first: today's messages precede boundary_in; within today, later received_at first
    ids_in_order = [m["message_id"] for m in default_days]
    assert ids_in_order.index("today_inbox_late") < ids_in_order.index("today_inbox_early")
    assert ids_in_order.index("today_inbox_early") < ids_in_order.index("boundary_in")

    sent_only = client.get("/api/mail/messages?folder=sent").json()
    assert {m["message_id"] for m in sent_only} == {"today_sent"}

    inbox_only = client.get("/api/mail/messages?folder=inbox").json()
    assert {m["message_id"] for m in inbox_only} == {"boundary_in", "today_inbox_early", "today_inbox_late"}

    clamped_low = client.get("/api/mail/messages?days=0").json()
    assert {m["message_id"] for m in clamped_low} == {"today_inbox_early", "today_inbox_late", "today_sent"}

    clamped_high = client.get("/api/mail/messages?days=99").json()
    assert {m["message_id"] for m in clamped_high} == {m["message_id"] for m in default_days}

    capped = client.get("/api/mail/messages?days=1").json()
    assert {m["message_id"] for m in capped} == {"today_inbox_early", "today_inbox_late", "today_sent"}


def test_sent_messages_are_ordered_newest_first(client, tmp_path):
    day0 = TODAY.isoformat()
    # deliberately out of order in the file; sent items carry no received_at
    messages = [
        _msg("sent_08", folder="sent", sent_at=f"{day0}T08:00:00Z"),
        _msg("sent_17", folder="sent", sent_at=f"{day0}T17:00:00Z"),
        _msg("sent_12", folder="sent", sent_at=f"{day0}T12:00:00Z"),
    ]
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox(messages)), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    ordered = [m["message_id"] for m in client.get("/api/mail/messages?folder=sent").json()]
    assert ordered == ["sent_17", "sent_12", "sent_08"]


def test_get_messages_triage_filter_and_enrichment(client, tmp_path):
    priya = client.post("/api/people", json={"name": "Priya Shah", "email": "priya.shah@bank.com"}).json()
    client.post(f"/api/people/{priya['id']}/aliases", json={"alias": "p.shah@partner.example"})
    dev = client.post("/api/people", json={"name": "Dev Kapoor", "email": "dev.kapoor@bank.com"}).json()

    messages = [
        _msg(
            "m1",
            received_at=f"{TODAY.isoformat()}T09:00:00Z",
            sender_email="PRIYA.SHAH@BANK.COM",
            to=[{"name": "Dev Kapoor", "email": "dev.kapoor@bank.com"}],
            cc=[{"name": "Via alias", "email": "P.SHAH@PARTNER.EXAMPLE"}],
        ),
        _msg("m2", received_at=f"{TODAY.isoformat()}T09:05:00Z", sender_email="nobody@bank.com"),
    ]
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox(messages)), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    by_message_id = {m["message_id"]: m for m in client.get("/api/mail/messages").json()}
    assert by_message_id["m1"]["sender_person"] == {"id": priya["id"], "name": "Priya Shah"}
    matched_ids = {p["id"] for p in by_message_id["m1"]["matched_people"]}
    assert matched_ids == {dev["id"], priya["id"]}

    matched_by_id = {p["id"]: p for p in by_message_id["m1"]["matched_people"]}
    # dev matched via his own (primary) email
    assert matched_by_id[dev["id"]]["matched_email"] == "dev.kapoor@bank.com"
    # priya matched via the cc alias address, not her primary email — matched_email
    # must carry the address that actually resolved her, lowercased
    assert matched_by_id[priya["id"]]["email"] == "priya.shah@bank.com"
    assert matched_by_id[priya["id"]]["matched_email"] == "p.shah@partner.example"

    assert by_message_id["m2"]["sender_person"] is None
    assert by_message_id["m2"]["matched_people"] == []

    # dismiss m2 directly (no triage-mutation endpoint exists in this work package)
    session = SessionLocal()
    try:
        _row(session, "m2").triage = "dismissed"
        session.commit()
    finally:
        session.close()

    pending = client.get("/api/mail/messages?triage=pending").json()
    assert {m["message_id"] for m in pending} == {"m1"}
    dismissed = client.get("/api/mail/messages?triage=dismissed").json()
    assert {m["message_id"] for m in dismissed} == {"m2"}


def test_stats_counts(client, tmp_path):
    messages = [
        _msg("s1", received_at=f"{TODAY.isoformat()}T09:00:00Z"),
        _msg("s2", received_at=f"{TODAY.isoformat()}T09:05:00Z"),
        _msg("s3", received_at=f"{TODAY.isoformat()}T09:10:00Z"),
        _msg("old", received_at=f"{(TODAY - timedelta(days=10)).isoformat()}T09:00:00Z"),
    ]
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox(messages)), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    session = SessionLocal()
    try:
        _row(session, "s2").triage = "linked"
        _row(session, "s3").triage = "dismissed"
        session.commit()
    finally:
        session.close()

    stats = client.get("/api/mail/stats").json()
    assert stats == {"pending": 1, "linked": 1, "dismissed": 1, "total": 3}


def test_stats_handles_unexpected_triage_value(client, tmp_path):
    msg = _msg("s1", received_at=f"{TODAY.isoformat()}T09:00:00Z")
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox([msg])), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    session = SessionLocal()
    try:
        # a value /mail/stats doesn't know about — must never 500
        _row(session, "s1").triage = "archived"
        session.commit()
    finally:
        session.close()

    resp = client.get("/api/mail/stats")
    assert resp.status_code == 200
    # counted in total, but does not appear as its own stray key
    assert resp.json() == {"pending": 0, "linked": 0, "dismissed": 0, "total": 1}


def test_clear_scope_mail_removes_rows_and_links(client, tmp_path):
    msg = _msg("m1", received_at=f"{TODAY.isoformat()}T09:00:00Z")
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox([msg])), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    session = SessionLocal()
    try:
        mail_row_id = _row(session, "m1").id
        session.add(Link(from_type="mail", from_id=mail_row_id, to_type="action", to_id=1, kind="relates"))
        session.commit()
    finally:
        session.close()

    assert client.post("/api/admin/clear", json={"scope": "mail", "confirm": "nope"}).status_code == 422

    result = client.post("/api/admin/clear", json={"scope": "mail", "confirm": "CLEAR"}).json()
    assert result == {"cleared": "mail", "rows": 1}

    assert client.get("/api/mail/messages").json() == []

    session = SessionLocal()
    try:
        remaining_links = (
            session.query(Link)
            .filter((Link.from_type == "mail") | (Link.to_type == "mail"))
            .count()
        )
        assert remaining_links == 0
    finally:
        session.close()


def test_mail_link_via_api_round_trips_and_protects_from_purge(client, tmp_path):
    """Proves the Phase-3 blocker is gone: a mail row can now be one end of a
    generic Link (integer from_id/to_id), the link is visible through the real
    /api/links endpoints (with the "mail" resolve_title case producing the
    subject), and its presence protects the message from retention purge even
    though the message's triage is still "pending"."""
    msg = _msg("linked-via-api", received_at=f"{TODAY.isoformat()}T09:00:00Z", subject="Needs follow-up")
    path = tmp_path / "mailbox.json"
    path.write_text(json.dumps(_mailbox([msg])), encoding="utf-8")
    client.post("/api/mail/import", json={"path": str(path)})

    message = next(m for m in client.get("/api/mail/messages").json() if m["message_id"] == "linked-via-api")
    mail_id = message["id"]
    assert isinstance(mail_id, int)

    action = client.post("/api/actions", json={"title": "Follow up on email"}).json()

    create = client.post(
        "/api/links",
        json={"from_type": "mail", "from_id": mail_id, "to_type": "action", "to_id": action["id"], "kind": "relates"},
    )
    assert create.status_code == 201
    link = create.json()
    assert link["from_type"] == "mail" and link["from_id"] == mail_id
    assert link["to_type"] == "action" and link["to_id"] == action["id"]
    # resolve_title's new "mail" case: from_title is the message subject
    assert link["from_title"] == "Needs follow-up"
    assert link["to_title"] == "Follow up on email"

    # round-trips through GET
    fetched = client.get(f"/api/links/for/mail/{mail_id}").json()
    assert len(fetched) == 1
    assert fetched[0]["id"] == link["id"]
    assert fetched[0]["to_id"] == action["id"]
    assert fetched[0]["from_title"] == "Needs follow-up"

    # age the message well past retention WITHOUT touching triage (still
    # "pending") — only the Link should be what keeps it alive
    old_date = (TODAY - timedelta(days=MAIL_RETENTION_DAYS + 10)).isoformat()
    session = SessionLocal()
    try:
        row = _row(session, "linked-via-api")
        assert row.triage == "pending"
        row.occurred_date = old_date
        row.received_at = f"{old_date}T09:00:00Z"
        session.commit()
    finally:
        session.close()

    # trigger another retention purge pass via a no-op import
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps(_mailbox([])), encoding="utf-8")
    summary = client.post("/api/mail/import", json={"path": str(empty_path)}).json()
    assert summary["purged"] == 0

    session = SessionLocal()
    try:
        assert _row(session, "linked-via-api") is not None
    finally:
        session.close()
