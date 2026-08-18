import json
from datetime import date, timedelta

TODAY = date.today()


def _mailbox(messages):
    return {"messages": messages}


def _msg(
    msg_id,
    folder="inbox",
    subject="Subject",
    sender_name="Alex Morgan",
    sender_email="alex.morgan@bank.com",
    to=None,
    cc=None,
    sent_at=None,
    received_at=None,
):
    if folder == "sent":
        sent_at = sent_at or f"{TODAY.isoformat()}T09:00:00Z"
    else:
        received_at = received_at or f"{TODAY.isoformat()}T09:00:00Z"
    return {
        "id": msg_id,
        "folder": folder,
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to": to or [],
        "cc": cc or [],
        "sent_at": sent_at,
        "received_at": received_at,
        "body_text": "body",
        "has_attachments": False,
    }


def _import_and_get(client, tmp_path, msg, filename="mailbox.json"):
    path = tmp_path / filename
    path.write_text(json.dumps(_mailbox([msg])), encoding="utf-8")
    resp = client.post("/api/mail/import", json={"path": str(path)})
    assert resp.status_code == 200, resp.text
    rows = client.get("/api/mail/messages").json()
    return next(r for r in rows if r["message_id"] == msg["id"])


def _person(client, name, email):
    return client.post("/api/people", json={"name": name, "email": email}).json()


def _action(client, title, owner_id=None, due_date=None):
    body = {"title": title}
    if owner_id is not None:
        body["owner_id"] = owner_id
    if due_date is not None:
        body["due_date"] = due_date
    return client.post("/api/actions", json=body).json()


def _commitment(client, title, owner_id=None, due_date=None):
    body = {"title": title}
    if owner_id is not None:
        body["owner_id"] = owner_id
    if due_date is not None:
        body["due_date"] = due_date
    return client.post("/api/commitments", json=body).json()


def _chase(client, action_id=None, commitment_id=None, next_chase_on=None):
    body = {
        "chased_on": (TODAY - timedelta(days=3)).isoformat(),
        "next_chase_on": next_chase_on,
    }
    if action_id is not None:
        body["action_id"] = action_id
    if commitment_id is not None:
        body["commitment_id"] = commitment_id
    resp = client.post("/api/chases", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- suggestions: scoring components ----------


def test_suggestions_owner_is_sender_on_inbox_mail(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    action = _action(client, "Prepare quarterly budget review", owner_id=sarah["id"])
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", folder="inbox", subject="Digest of internal newsletter updates",
             sender_email="sarah.chen@bank.com"),
    )

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1
    item = suggestions[0]
    assert item["type"] == "action"
    assert item["id"] == action["id"]
    assert item["score"] == 3.0
    assert item["reasons"] == ["Owned by Sarah Chen (sender)"]
    assert item["owner"] == {"id": sarah["id"], "name": "Sarah Chen"}


def test_suggestions_owner_is_sender_bonus_does_not_apply_on_sent_mail(client, tmp_path):
    # the "owner is sender" bonus is inbox-only: on a sent mail the mailbox
    # owner is the sender, so this component must not fire even though the
    # action's owner happens to equal the (self) sender address
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    _action(client, "Prepare quarterly budget review", owner_id=sarah["id"])
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", folder="sent", subject="Digest of internal newsletter updates",
             sender_email="sarah.chen@bank.com"),
    )
    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    assert resp.json()["suggestions"] == []


def test_suggestions_owner_among_recipients_on_sent_mail(client, tmp_path):
    tom = _person(client, "Tom Okafor", "tom.okafor@bank.com")
    commitment = _commitment(client, "Chase supplier invoice", owner_id=tom["id"])
    mail = _import_and_get(
        client, tmp_path,
        _msg(
            "m1", folder="sent", subject="Digest of internal newsletter updates",
            sender_email="delegate@bank.com",
            to=[{"name": "Tom Okafor", "email": "tom.okafor@bank.com"}],
        ),
    )

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1
    item = suggestions[0]
    assert item["type"] == "commitment"
    assert item["id"] == commitment["id"]
    assert item["score"] == 3.0
    assert item["reasons"] == ["Sent to owner Tom Okafor"]


def test_suggestions_owner_among_recipients_on_inbox_mail(client, tmp_path):
    priya = _person(client, "Priya Shah", "priya.shah@bank.com")
    action = _action(client, "Fix leaking pipe valve", owner_id=priya["id"])
    mail = _import_and_get(
        client, tmp_path,
        _msg(
            "m1", folder="inbox", subject="Digest of internal newsletter updates",
            sender_email="external@partner.example",
            cc=[{"name": "Priya Shah", "email": "priya.shah@bank.com"}],
        ),
    )

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1
    item = suggestions[0]
    assert item["id"] == action["id"]
    assert item["score"] == 2.0
    assert item["reasons"] == ["Also addressed to owner Priya Shah"]


def test_suggestions_chase_due(client, tmp_path):
    action = _action(client, "Chase supplier invoice")
    _chase(client, action_id=action["id"], next_chase_on=TODAY.isoformat())
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", subject="Digest of internal newsletter updates"),
    )

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["id"] == action["id"]
    assert suggestions[0]["score"] == 2.0
    assert suggestions[0]["reasons"] == ["Chase due"]


def test_suggestions_chase_not_yet_due_does_not_score(client, tmp_path):
    action = _action(client, "Chase supplier invoice")
    _chase(client, action_id=action["id"], next_chase_on=(TODAY + timedelta(days=5)).isoformat())
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", subject="Digest of internal newsletter updates"),
    )
    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    assert resp.json()["suggestions"] == []


def test_suggestions_due_window_soon_and_overdue(client, tmp_path):
    soon = _action(client, "Book travel for offsite", due_date=(TODAY + timedelta(days=3)).isoformat())
    overdue = _action(client, "Sharpen kitchen knives", due_date=(TODAY - timedelta(days=2)).isoformat())
    far = _action(client, "Walk the dog outside", due_date=(TODAY + timedelta(days=30)).isoformat())
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", subject="Digest of internal newsletter updates"),
    )

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    by_id = {item["id"]: item for item in resp.json()["suggestions"]}
    assert far["id"] not in by_id  # 30 days out — no due-window bonus, no other component
    assert by_id[soon["id"]]["score"] == 1.0
    assert by_id[soon["id"]]["reasons"] == [f"Due {soon['due_date']}"]
    assert by_id[overdue["id"]]["score"] == 1.0
    assert by_id[overdue["id"]]["reasons"] == ["Overdue"]


def test_suggestions_title_similarity_threshold(client, tmp_path):
    subject = "Quarterly budget review pack for finance leadership"
    similar = _action(client, "Quarterly budget review pack finance")
    dissimilar = _action(client, "Sharpen kitchen knives")
    mail = _import_and_get(client, tmp_path, _msg("m1", subject=subject))

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    suggestions = resp.json()["suggestions"]
    ids = {item["id"] for item in suggestions}
    assert similar["id"] in ids
    assert dissimilar["id"] not in ids
    item = next(i for i in suggestions if i["id"] == similar["id"])
    assert item["reasons"] == ["Title similar to subject"]
    assert item["score"] > 0


def test_suggestions_404_unknown_mail(client):
    resp = client.get("/api/mail/999999/suggestions")
    assert resp.status_code == 404


def test_suggestions_ordering_top6_cap_and_zero_exclusion(client, tmp_path):
    subject = "Digest of internal newsletter updates"
    mail = _import_and_get(client, tmp_path, _msg("m1", subject=subject))

    item1 = _action(client, "Prepare quarterly budget review",
                     due_date=(TODAY + timedelta(days=2)).isoformat())
    _chase(client, action_id=item1["id"], next_chase_on=TODAY.isoformat())  # 2.0 + 1.0 = 3.0

    item2 = _action(client, "Chase supplier invoice")
    _chase(client, action_id=item2["id"], next_chase_on=TODAY.isoformat())  # 2.0

    item3 = _action(client, "Fix leaking pipe valve", due_date=(TODAY + timedelta(days=1)).isoformat())  # 1.0
    item4 = _action(client, "Book travel for offsite", due_date=(TODAY + timedelta(days=5)).isoformat())  # 1.0
    item5 = _action(client, "Sharpen kitchen knives", due_date=(TODAY - timedelta(days=1)).isoformat())  # 1.0 overdue
    item7 = _action(client, "Nothing to see here", due_date=(TODAY + timedelta(days=6)).isoformat())  # 1.0
    item8 = _action(client, "Walk the dog outside", due_date=(TODAY + timedelta(days=7)).isoformat())  # 1.0 boundary

    # scores 0 across the board: no owner match, no chase, no due date, dissimilar title
    _action(client, "Paint garage door blue")

    resp = client.get(f"/api/mail/{mail['id']}/suggestions")
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 6

    ids_in_order = [s["id"] for s in suggestions]
    assert ids_in_order == [
        item1["id"], item2["id"], item5["id"], item3["id"], item4["id"], item7["id"],
    ]
    assert item8["id"] not in ids_in_order  # 7th by (score desc, due_date asc) — dropped by the top-6 cap
    assert suggestions[0]["score"] == 3.0
    assert suggestions[1]["score"] == 2.0
    for s in suggestions[2:]:
        assert s["score"] == 1.0


# ---------- log-chase ----------


def test_log_chase_happy_path(client, tmp_path):
    action = _action(client, "Chase supplier invoice")
    past_date = (TODAY - timedelta(days=2)).isoformat()
    mail = _import_and_get(
        client, tmp_path,
        _msg("m1", subject="Please chase this", received_at=f"{past_date}T09:00:00Z"),
    )

    resp = client.post(
        f"/api/mail/{mail['id']}/log-chase",
        json={"target_type": "action", "target_id": action["id"], "note": None, "next_chase_on": "2026-09-01"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_type"] == "action"
    assert body["target_id"] == action["id"]

    chases = client.get(f"/api/chases?action_id={action['id']}").json()
    assert len(chases) == 1
    chase = chases[0]
    assert chase["id"] == body["chase_id"]
    assert chase["chased_on"] == past_date  # from mail.occurred_date, not today
    assert chase["method"] == "email"
    assert chase["note"] == "Chased via email: Please chase this"
    assert chase["next_chase_on"] == "2026-09-01"

    links = client.get(f"/api/links/for/mail/{mail['id']}").json()
    assert len(links) == 1
    assert links[0]["from_type"] == "mail" and links[0]["from_id"] == mail["id"]
    assert links[0]["to_type"] == "action" and links[0]["to_id"] == action["id"]
    assert links[0]["kind"] == "informs"
    assert links[0]["rationale"] == "Chase logged from email"

    updated_mail = next(
        m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"]
    )
    assert updated_mail["triage"] == "linked"
    assert updated_mail["triaged_at"] is not None


def test_log_chase_with_custom_note_and_commitment_target(client, tmp_path):
    commitment = _commitment(client, "Deliver report")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    resp = client.post(
        f"/api/mail/{mail['id']}/log-chase",
        json={"target_type": "commitment", "target_id": commitment["id"], "note": "Custom note", "next_chase_on": None},
    )
    assert resp.status_code == 200
    chases = client.get(f"/api/chases?commitment_id={commitment['id']}").json()
    assert chases[0]["note"] == "Custom note"
    assert chases[0]["next_chase_on"] is None


def test_log_chase_404_unknown_mail(client):
    resp = client.post(
        "/api/mail/999999/log-chase",
        json={"target_type": "action", "target_id": 1, "note": None, "next_chase_on": None},
    )
    assert resp.status_code == 404


def test_log_chase_404_unknown_target(client, tmp_path):
    mail = _import_and_get(client, tmp_path, _msg("m1"))
    resp = client.post(
        f"/api/mail/{mail['id']}/log-chase",
        json={"target_type": "action", "target_id": 999999, "note": None, "next_chase_on": None},
    )
    assert resp.status_code == 404


def test_log_chase_422_bad_target_type(client, tmp_path):
    mail = _import_and_get(client, tmp_path, _msg("m1"))
    resp = client.post(
        f"/api/mail/{mail['id']}/log-chase",
        json={"target_type": "topic", "target_id": 1, "note": None, "next_chase_on": None},
    )
    assert resp.status_code == 422


# ---------- create-action ----------


def test_create_action_happy_path(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    resp = client.post(
        f"/api/mail/{mail['id']}/create-action",
        json={"text": "Follow up on contract @sarah due:tomorrow !high"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Follow up on contract"
    assert body["owner_name"] == "Sarah Chen"
    assert body["due_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert body["warnings"] == []

    action = client.get(f"/api/actions/{body['action_id']}").json()
    assert action["owner"]["id"] == sarah["id"]
    assert action["priority"] == "high"

    links = client.get(f"/api/links/for/mail/{mail['id']}").json()
    assert len(links) == 1
    assert links[0]["to_type"] == "action" and links[0]["to_id"] == body["action_id"]
    assert links[0]["rationale"] == "Created from email"

    updated_mail = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert updated_mail["triage"] == "linked"
    assert updated_mail["triaged_at"] is not None


def test_create_action_422_empty_title(client, tmp_path):
    mail = _import_and_get(client, tmp_path, _msg("m1"))
    resp = client.post(f"/api/mail/{mail['id']}/create-action", json={"text": "@nobody due:tomorrow"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "No title after removing tokens"


def test_create_action_404_unknown_mail(client):
    resp = client.post("/api/mail/999999/create-action", json={"text": "Follow up"})
    assert resp.status_code == 404


# ---------- close-action ----------


def test_close_action_happy_path(client, tmp_path):
    action = _action(client, "Follow up on contract")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    resp = client.post(f"/api/mail/{mail['id']}/close-action", json={"action_id": action["id"]})
    assert resp.status_code == 200
    assert resp.json() == {"action_id": action["id"], "status": "done"}

    updated_action = client.get(f"/api/actions/{action['id']}").json()
    assert updated_action["status"] == "done"

    links = client.get(f"/api/links/for/mail/{mail['id']}").json()
    assert len(links) == 1
    assert links[0]["rationale"] == "Closed with evidence from email"

    updated_mail = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert updated_mail["triage"] == "linked"


def test_close_action_404_unknown_mail_or_action(client, tmp_path):
    action = _action(client, "Follow up on contract")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    assert client.post("/api/mail/999999/close-action", json={"action_id": action["id"]}).status_code == 404
    assert client.post(f"/api/mail/{mail['id']}/close-action", json={"action_id": 999999}).status_code == 404


# ---------- person-note ----------


def test_person_note_happy_path(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    resp = client.post(
        f"/api/mail/{mail['id']}/person-note",
        json={"person_id": sarah["id"], "kind": "feedback", "note": "Great collaboration this week"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["person_id"] == sarah["id"]
    assert body["kind"] == "feedback"
    assert body["note"] == "Great collaboration this week"
    assert body["noted_on"] == TODAY.isoformat()
    assert body["source"] == "mail"

    links = client.get(f"/api/links/for/mail/{mail['id']}").json()
    assert len(links) == 1
    assert links[0]["to_type"] == "person_note" and links[0]["to_id"] == body["id"]
    assert links[0]["kind"] == "relates"
    assert links[0]["rationale"] == "Noted from email"
    assert links[0]["to_title"] == "Great collaboration this week"[:60]

    updated_mail = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert updated_mail["triage"] == "linked"


def test_person_note_default_kind(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    mail = _import_and_get(client, tmp_path, _msg("m1"))
    resp = client.post(
        f"/api/mail/{mail['id']}/person-note", json={"person_id": sarah["id"], "note": "General note"}
    )
    assert resp.json()["kind"] == "general"


def test_person_note_422_empty(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    mail = _import_and_get(client, tmp_path, _msg("m1"))
    resp = client.post(
        f"/api/mail/{mail['id']}/person-note", json={"person_id": sarah["id"], "note": "   "}
    )
    assert resp.status_code == 422


def test_person_note_404_unknown_mail_or_person(client, tmp_path):
    sarah = _person(client, "Sarah Chen", "sarah.chen@bank.com")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    assert client.post(
        "/api/mail/999999/person-note", json={"person_id": sarah["id"], "note": "note"}
    ).status_code == 404
    assert client.post(
        f"/api/mail/{mail['id']}/person-note", json={"person_id": 999999, "note": "note"}
    ).status_code == 404


# ---------- dismiss / reopen / bulk ----------


def test_dismiss_and_reopen(client, tmp_path):
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    resp = client.post(f"/api/mail/{mail['id']}/dismiss")
    assert resp.status_code == 200
    assert resp.json() == {"triage": "dismissed"}
    dismissed = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert dismissed["triage"] == "dismissed"
    assert dismissed["triaged_at"] is not None

    resp = client.post(f"/api/mail/{mail['id']}/reopen")
    assert resp.status_code == 200
    assert resp.json() == {"triage": "pending"}
    reopened = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert reopened["triage"] == "pending"
    assert reopened["triaged_at"] is None


def test_dismiss_bulk(client, tmp_path):
    m1 = _import_and_get(client, tmp_path, _msg("m1"), filename="mb1.json")
    m2 = _import_and_get(client, tmp_path, _msg("m2"), filename="mb2.json")
    m3 = _import_and_get(client, tmp_path, _msg("m3"), filename="mb3.json")
    client.post(f"/api/mail/{m3['id']}/dismiss")  # already dismissed — shouldn't be double-counted

    resp = client.post("/api/mail/dismiss-bulk", json={"ids": [m1["id"], m2["id"], m3["id"], 999999]})
    assert resp.status_code == 200
    assert resp.json() == {"dismissed": 2}

    rows = {m["id"]: m for m in client.get("/api/mail/messages").json()}
    assert rows[m1["id"]]["triage"] == "dismissed"
    assert rows[m2["id"]]["triage"] == "dismissed"
    assert rows[m3["id"]]["triage"] == "dismissed"


# ---------- verbs work on already-linked mail (relink adds another Link) ----------


def test_verbs_on_already_linked_mail_add_second_link(client, tmp_path):
    action1 = _action(client, "First action")
    action2 = _action(client, "Second action")
    mail = _import_and_get(client, tmp_path, _msg("m1"))

    client.post(f"/api/mail/{mail['id']}/close-action", json={"action_id": action1["id"]})
    linked_mail = next(m for m in client.get("/api/mail/messages").json() if m["id"] == mail["id"])
    assert linked_mail["triage"] == "linked"

    resp = client.post(f"/api/mail/{mail['id']}/close-action", json={"action_id": action2["id"]})
    assert resp.status_code == 200

    links = client.get(f"/api/links/for/mail/{mail['id']}").json()
    assert len(links) == 2
    to_ids = {link["to_id"] for link in links}
    assert to_ids == {action1["id"], action2["id"]}
