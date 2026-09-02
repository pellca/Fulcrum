def test_full_lifecycle(client):
    # seed demo data
    seeded = client.post("/api/admin/seed").json()
    assert seeded["commitments"] >= 4

    # dashboard aggregates
    summary = client.get("/api/dashboard/summary").json()
    assert summary["chase_queue"], "seed should produce chases due"

    # agenda flow: candidates -> add top candidate -> capacity respected in payload
    meetings = client.get("/api/meetings").json()
    assert meetings, "seed should produce meetings"
    meeting_id = meetings[0]["id"]
    candidates = client.get(f"/api/meetings/{meeting_id}/candidates").json()
    assert candidates[0]["score"] >= candidates[-1]["score"]
    top = candidates[0]["topic"]
    meeting = client.post(f"/api/meetings/{meeting_id}/agenda", json={"topic_id": top["id"]}).json()
    assert len(meeting["agenda_items"]) == 1
    assert meeting["agenda_items"][0]["allocated_minutes"] == top["duration_minutes"]
    # topic no longer a candidate
    remaining = client.get(f"/api/meetings/{meeting_id}/candidates").json()
    assert all(c["topic"]["id"] != top["id"] for c in remaining)

    # duplicate add rejected
    assert client.post(f"/api/meetings/{meeting_id}/agenda", json={"topic_id": top["id"]}).status_code == 409

    # quickadd creates a real action
    created = client.post("/api/quickadd", json={"text": "Test the thing @sarah due:+3", "type": "action"}).json()
    action = client.get(f"/api/actions/{created['id']}").json()
    assert action["owner"]["name"] == "Sarah Chen"

    # risk chains exist (seed has a blocked action upstream of a commitment)
    risks = client.get("/api/planner/risks").json()
    assert any(r["cause_reason"] == "blocked" for r in risks)

    # timeline has lanes and meetings
    timeline = client.get("/api/planner/timeline?weeks=8").json()
    assert timeline["lanes"] and timeline["meetings"]

    # clearing demo keeps the real quickadd action, then full clear resets schema
    client.post("/api/admin/clear", json={"scope": "demo", "confirm": "CLEAR"})
    assert client.get(f"/api/actions/{created['id']}").status_code == 200
    assert client.get("/api/commitments").json() == []

    assert client.post("/api/admin/clear", json={"scope": "all", "confirm": "nope"}).status_code == 422
    client.post("/api/admin/clear", json={"scope": "all", "confirm": "CLEAR"})
    assert client.get("/api/actions").json() == []
    # schema intact after full clear
    assert client.post("/api/people", json={"name": "New Person"}).status_code == 201


def test_one_to_one_pack(client):
    client.post("/api/admin/seed")
    person = next(p for p in client.get("/api/people").json() if p["name"] == "Sarah Chen")
    pack = client.get(f"/api/people/{person['id']}/pack").json()
    assert pack["person"]["name"] == "Sarah Chen"
    all_titles = [i["title"] for i in pack["overdue"] + pack["due_soon"] + pack["later"]]
    assert "Agree revised credit risk audit scope with 2LoD" in all_titles
    assert any(t["title"].startswith("Credit scope change") for t in pack["topics"])
    assert client.get("/api/people/99999/pack").status_code == 404


def test_decision_review_dates(client):
    client.post("/api/people", json={"name": "Alex Morgan"})
    created = client.post(
        "/api/decisions",
        json={"title": "Revisit hybrid working stance", "review_on": "2020-01-01"},
    ).json()
    assert created["review_on"] == "2020-01-01"

    summary = client.get("/api/dashboard/summary").json()
    due = summary["decisions_for_review"]
    assert any(d["id"] == created["id"] and d["days_overdue"] > 0 for d in due)

    # clearing the review date removes it from the queue
    client.patch(f"/api/decisions/{created['id']}", json={"review_on": None})
    summary = client.get("/api/dashboard/summary").json()
    assert all(d["id"] != created["id"] for d in summary["decisions_for_review"])


def test_capacity_heatmap(client):
    client.post("/api/admin/seed")
    data = client.get("/api/planner/capacity?weeks=4").json()
    assert len(data["weeks"]) == 4
    rows = {r["person"]["name"]: r for r in data["rows"]}
    assert "Sarah Chen" in rows and "Tom Okafor" in rows
    tom = rows["Tom Okafor"]
    assert tom["overdue"]["count"] >= 2  # seeded overdue MI items
    assert all(row["total"] >= 1 for row in data["rows"])
    # rows sorted by load, heaviest first
    totals = [r["total"] for r in data["rows"]]
    assert totals == sorted(totals, reverse=True)


def test_topic_csv_import_and_recurring_agenda(client):
    client.post("/api/people", json={"name": "Priya Shah"})
    csv_content = (
        "type,title,description,intent,duration_minutes,owner,due,readiness,recurring\n"
        "topic,Monthly Performance Review,Standing MI review,inform,20,Priya Shah,,ready,yes\n"
        "topic,One-off deep dive,,decide,30,Priya Shah,2026-08-20,ready,\n"
    )
    preview = client.post(
        "/api/imports/planner/preview", files={"file": ("topics.csv", csv_content, "text/csv")}
    ).json()
    assert [i["type"] for i in preview["items"]] == ["topic", "topic"]
    assert preview["items"][0]["recurring"] is True and preview["items"][0]["duration_minutes"] == 20

    result = client.post("/api/imports/planner/commit", json={"items": preview["items"]}).json()
    assert result["created"]["topics"] == 2

    topics = {t["title"]: t for t in client.get("/api/topics").json()}
    standing = topics["Monthly Performance Review"]
    assert standing["recurring"] is True and standing["readiness"] == "ready"

    # recurring topic stays a candidate across meetings; one-off is consumed
    forum_id = client.post("/api/forums", json={"name": "Monthly Session", "capacity_minutes": 60}).json()["id"]
    m1 = client.post("/api/meetings", json={"forum_id": forum_id, "scheduled_at": "2026-08-03T10:00:00"}).json()["id"]
    m2 = client.post("/api/meetings", json={"forum_id": forum_id, "scheduled_at": "2026-09-07T10:00:00"}).json()["id"]

    client.post(f"/api/meetings/{m1}/agenda", json={"topic_id": standing["id"]})
    client.post(f"/api/meetings/{m1}/agenda", json={"topic_id": topics["One-off deep dive"]["id"]})
    assert client.get(f"/api/topics").json()  # sanity
    m2_candidates = {c["topic"]["title"]: c for c in client.get(f"/api/meetings/{m2}/candidates").json()}
    assert "Monthly Performance Review" in m2_candidates
    assert "Standing item" in m2_candidates["Monthly Performance Review"]["reasons"]
    assert "One-off deep dive" not in m2_candidates
    # status untouched for the standing item, consumed for the one-off
    topics_after = {t["title"]: t for t in client.get("/api/topics").json()}
    assert topics_after["Monthly Performance Review"]["status"] == "proposed"
    assert topics_after["One-off deep dive"]["status"] == "scheduled"
    # and it can be added to the second meeting too
    assert client.post(f"/api/meetings/{m2}/agenda", json={"topic_id": standing["id"]}).status_code == 200


def test_topic_import_without_type_column(client):
    """A topics CSV with no `type` column must not import as actions."""
    csv_content = (
        "title,description,intent,duration_minutes,readiness,recurring\n"
        "Quarterly risk deep dive,,consult,30,ready,\n"
    )
    # explicit page context wins
    preview = client.post(
        "/api/imports/planner/preview?default_type=topic",
        files={"file": ("topics.csv", csv_content, "text/csv")},
    ).json()
    assert preview["items"][0]["type"] == "topic"
    assert preview["type_column_present"] is False

    # and even without it, topic-only columns are inferred
    inferred = client.post(
        "/api/imports/planner/preview", files={"file": ("topics.csv", csv_content, "text/csv")}
    ).json()
    assert inferred["default_type"] == "topic"
    assert inferred["items"][0]["type"] == "topic"

    created = client.post("/api/imports/planner/commit", json={"items": inferred["items"]}).json()
    assert created["created"] == {"actions": 0, "commitments": 0, "topics": 1, "meeting_links": 0}
    assert client.get("/api/actions").json() == []

    # a plain action CSV still imports as actions
    action_csv = "title,owner,due,status,priority\nBook the room,,2026-08-01,Not started,low\n"
    plain = client.post(
        "/api/imports/planner/preview", files={"file": ("a.csv", action_csv, "text/csv")}
    ).json()
    assert plain["items"][0]["type"] == "action"
    # an explicit type value always beats the page default
    mixed = "type,title,intent\ncommitment,Promised thing,\n"
    override = client.post(
        "/api/imports/planner/preview?default_type=topic",
        files={"file": ("m.csv", mixed, "text/csv")},
    ).json()
    assert override["items"][0]["type"] == "commitment"


def test_bulk_delete_and_reference_checks(client):
    client.post("/api/admin/seed")
    actions = client.get("/api/actions").json()
    ids = [a["id"] for a in actions[:3]]

    check = client.post("/api/bulk/check", json={"type": "action", "ids": ids}).json()
    assert check["found"] == 3 and check["label"] == "actions"
    assert any("chase" in w["label"] for w in check["warnings"])

    result = client.post("/api/bulk/delete", json={"type": "action", "ids": ids}).json()
    assert result["deleted"] == 3
    remaining = {a["id"] for a in client.get("/api/actions").json()}
    assert not remaining & set(ids)
    # links pointing at deleted actions are pruned, not left dangling
    for link in client.get("/api/links/for/commitment/1").json():
        assert not (link["from_type"] == "action" and link["from_id"] in ids)

    assert client.post("/api/bulk/delete", json={"type": "nonsense", "ids": [1]}).status_code == 422


def test_person_delete_warns_about_orphans(client):
    client.post("/api/admin/seed")
    person = next(p for p in client.get("/api/people").json() if p["name"] == "Sarah Chen")

    refs = client.get(f"/api/people/{person['id']}/references").json()
    labels = {w["label"]: w for w in refs["warnings"]}
    assert labels["open actions owned"]["count"] >= 1
    assert labels["open commitments owned"]["count"] >= 1
    assert labels["topics sponsored"]["count"] >= 1
    assert labels["open actions owned"]["examples"]

    client.delete(f"/api/people/{person['id']}")
    assert client.get(f"/api/people/{person['id']}/references").status_code == 404
    # their items survive, now unowned
    orphaned = [a for a in client.get("/api/actions").json() if a["owner"] is None]
    assert orphaned


def test_people_csv_import(client):
    client.post("/api/people", json={"name": "Sarah Chen"})
    csv_content = (
        "name,email,team,role,is_bpm,aliases\n"
        "Sarah Chen,sarah@bank.com,Credit,Audit Director,,Chen Sarah\n"
        "New Bpm,bpm@bank.com,COO,Business Manager,yes,NB;Bpm New\n"
        "New Bpm,dupe@bank.com,,,,\n"
        ",,,,,\n"
    )
    preview = client.post(
        "/api/imports/people/preview", files={"file": ("people.csv", csv_content, "text/csv")}
    ).json()
    assert preview["skipped"] == 1  # in-file duplicate (fully blank rows are dropped pre-parse)
    by_name = {i["name"]: i for i in preview["items"]}
    assert by_name["Sarah Chen"]["exists"] is True
    assert by_name["New Bpm"]["exists"] is False and by_name["New Bpm"]["is_bpm"] is True

    result = client.post("/api/imports/people/commit", json={"items": preview["items"]}).json()
    assert result == {"created": 1, "skipped_existing": 1, "aliases_added": 3}

    people = {p["name"]: p for p in client.get("/api/people").json()}
    assert people["New Bpm"]["is_bpm"] is True
    assert {a["alias"] for a in people["Sarah Chen"]["aliases"]} == {"Chen Sarah"}
    # re-import is idempotent
    again = client.post("/api/imports/people/commit", json={"items": preview["items"]}).json()
    assert again["created"] == 0 and again["aliases_added"] == 0


def test_convert_action_and_commitment(client):
    client.post("/api/people", json={"name": "Sarah Chen"})
    person_id = client.get("/api/people").json()[0]["id"]
    parent = client.post("/api/commitments", json={"title": "Parent commitment"}).json()
    action = client.post(
        "/api/actions",
        json={
            "title": "Deliver scope pack",
            "owner_id": person_id,
            "commitment_id": parent["id"],
            "due_date": "2026-08-10",
            "status": "blocked",
            "priority": "high",
            "notes": "Waiting on 2LoD",
        },
    ).json()
    client.post(
        "/api/chases",
        json={"action_id": action["id"], "chased_on": "2026-07-27", "note": "nudged", "next_chase_on": "2026-08-01"},
    )
    client.post(
        "/api/links",
        json={"from_type": "action", "from_id": action["id"], "to_type": "commitment", "to_id": parent["id"], "kind": "precedes"},
    )

    # action -> commitment: status maps, chases + links move, notes preserved
    converted = client.post(f"/api/actions/{action['id']}/convert", json={"origin": "aet"}).json()
    assert converted["status"] == "at_risk"
    assert converted["origin"] == "aet"
    assert "[Notes] Waiting on 2LoD" in converted["description"]
    assert converted["next_chase_on"] == "2026-08-01"
    assert client.get(f"/api/actions/{action['id']}").status_code == 404
    chases = client.get(f"/api/chases?commitment_id={converted['id']}").json()
    assert len(chases) == 1
    links = client.get(f"/api/links/for/commitment/{converted['id']}").json()
    assert any(l["kind"] == "precedes" for l in links)

    # commitment -> action: status maps back, chases follow again
    back = client.post(f"/api/commitments/{converted['id']}/convert").json()
    assert back["status"] == "blocked"
    assert "Origin before conversion: aet" in back["notes"]
    assert client.get(f"/api/commitments/{converted['id']}").status_code == 404
    assert len(client.get(f"/api/chases?action_id={back['id']}").json()) == 1

    # converting a commitment that has delivery actions keeps a relates link to them
    child = client.post("/api/actions", json={"title": "Child task", "commitment_id": parent["id"]}).json()
    parent_as_action = client.post(f"/api/commitments/{parent['id']}/convert").json()
    child_links = client.get(f"/api/links/for/action/{child['id']}").json()
    assert any(l["from_id"] == parent_as_action["id"] and l["kind"] == "relates" for l in child_links)
    assert client.get(f"/api/actions/{child['id']}").json()["commitment"] is None


def test_global_search(client):
    client.post("/api/admin/seed")

    result = client.get("/api/search", params={"q": "S166"}).json()
    types = {r["type"] for r in result["results"]}
    # S166 appears across the whole graph in the seed
    assert {"action", "commitment", "topic", "key_date", "workstream", "decision"} <= types
    assert result["count"] > 5

    # chase notes are searchable and resolve to their parent item
    chase_hits = client.get("/api/search", params={"q": "data extract"}).json()["results"]
    chase = next(r for r in chase_hits if r["type"] == "chase")
    assert chase["title"] == "Collate evidence annexes for S166 pack"
    assert chase["url"].startswith("/register?open=action-")
    assert "data extract" in chase["snippet"].lower()

    # people resolve to their 1:1 pack
    person_hits = client.get("/api/search", params={"q": "sarah"}).json()["results"]
    assert any(r["type"] == "person" and r["url"].endswith("/pack") for r in person_hits)

    # LIKE wildcards in the query are treated literally, and short queries rejected
    assert client.get("/api/search", params={"q": "%"}).status_code == 422
    assert client.get("/api/search", params={"q": "100%"}).json()["count"] == 0


def test_planner_csv_import(client):
    client.post("/api/people", json={"name": "Priya Shah"})
    client.post("/api/workstreams", json={"name": "Methodology"})

    csv_content = (
        "Task Name,Bucket Name,Progress,Priority,Assigned To,Due Date,Description\n"
        "Draft pilot plan,Methodology,In progress,Important,Priya Shah;Someone Else,2026-08-15,First cut\n"
        "Orphan task,,Not started,Low,Nobody Known,,\n"
        ",,,,,,\n"
    )
    preview = client.post(
        "/api/imports/planner/preview",
        files={"file": ("plan.csv", csv_content, "text/csv")},
    ).json()
    assert len(preview["items"]) == 2
    first = preview["items"][0]
    assert first["owner_matched"] and first["workstream_id"] is not None
    assert first["status"] == "in_progress" and first["priority"] == "high"
    assert preview["items"][1]["owner_matched"] is False

    result = client.post("/api/imports/planner/commit", json={"items": preview["items"]}).json()
    assert result["created"]["actions"] == 2
    actions = client.get("/api/actions").json()
    assert any(a["title"] == "Draft pilot plan" and a["due_date"] == "2026-08-15" for a in actions)


def test_copilot_csv_with_types_and_meeting_links(client):
    client.post("/api/people", json={"name": "Sarah Chen"})
    forum_id = client.post("/api/forums", json={"name": "AET Weekly"}).json()["id"]
    meeting_id = client.post(
        "/api/meetings", json={"forum_id": forum_id, "scheduled_at": "2026-08-03T10:00:00"}
    ).json()["id"]

    csv_content = (
        "type,title,description,owner,workstream,due,priority,origin,meeting\n"
        'commitment,Deliver scope pack,"Asked by CAE, urgent",Sarah Chen,,2026-08-10,high,principal,AET Weekly 2026-08-03\n'
        "action,Book walkthrough,,Sarah Chen,,2026-08-05,medium,,\n"
    )
    preview = client.post(
        "/api/imports/planner/preview",
        files={"file": ("copilot.csv", csv_content, "text/csv")},
    ).json()
    assert preview["items"][0]["type"] == "commitment"
    assert preview["items"][0]["origin"] == "principal"
    assert preview["items"][0]["meeting_id"] == meeting_id
    assert preview["items"][0]["meeting_matched"] is True
    assert preview["items"][1]["type"] == "action"

    # second row has no meeting column value -> default_meeting_id applies
    result = client.post(
        "/api/imports/planner/commit",
        json={"items": preview["items"], "default_meeting_id": meeting_id},
    ).json()
    assert result["created"] == {"actions": 1, "commitments": 1, "topics": 0, "meeting_links": 2}

    commitment = client.get("/api/commitments").json()[0]
    links = client.get(f"/api/links/for/commitment/{commitment['id']}").json()
    assert any(l["from_type"] == "meeting" and l["from_id"] == meeting_id for l in links)


def test_copilot_prompt_contains_live_context(client):
    client.post("/api/people", json={"name": "Lena Kovacs"})
    client.post("/api/workstreams", json={"name": "S166 Response"})
    client.post("/api/forums", json={"name": "Audit Committee Prep"})
    prompt = client.get("/api/imports/copilot-prompt").text
    assert "type,title,description,owner,workstream,due,priority,origin,meeting" in prompt
    assert "Lena Kovacs" in prompt
    assert "S166 Response" in prompt
    assert "Audit Committee Prep" in prompt


def test_templates_and_modules(client):
    template = client.get("/api/imports/templates/actions")
    assert template.status_code == 200 and template.text.startswith("type,title,")
    assert client.get("/api/imports/templates/nope").status_code == 404

    modules = client.get("/api/modules").json()
    names = {m["name"] for m in modules}
    assert {"diary-import", "outlook-diary-extractor"} <= names
    extractor = next(m for m in modules if m["name"] == "outlook-diary-extractor")
    assert extractor["available"] is False  # we're not on Windows

    # missing required arg rejected
    assert client.post("/api/modules/diary-import/run", json={"args": {}}).status_code == 422
    # unavailable platform rejected
    assert client.post("/api/modules/outlook-diary-extractor/run", json={"args": {"mailbox": "x", "out_file": "y"}}).status_code == 409


def test_unknown_api_paths_404_not_405_or_spa(client):
    # unknown API path: 404 with a JSON detail, never the GET-only SPA fallback
    unknown_get = client.get("/api/definitely-not-a-route")
    assert unknown_get.status_code == 404
    assert unknown_get.headers["content-type"].startswith("application/json")
    assert "<html" not in unknown_get.text.lower()

    # non-GET on an unknown path used to fall to the SPA catch-all and 405
    for call in (
        client.post("/api/definitely-not-a-route", json={}),
        client.put("/api/definitely-not-a-route", json={}),
        client.patch("/api/definitely-not-a-route", json={}),
        client.delete("/api/definitely-not-a-route"),
    ):
        assert call.status_code == 404

    # the guard must not shadow the docs/schema routes or any real endpoint
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200
    assert client.get("/api/people").status_code == 200


# ---------- register picker ----------


def test_register_picker_open_only_and_shape(client):
    priya = client.post("/api/people", json={"name": "Priya Shah"}).json()
    open_action = client.post(
        "/api/actions", json={"title": "Budget review pack", "owner_id": priya["id"], "due_date": "2026-09-01"}
    ).json()
    client.post("/api/actions", json={"title": "Budget closed item", "status": "done"})
    open_commitment = client.post("/api/commitments", json={"title": "Budget delivery commitment"}).json()
    client.post("/api/commitments", json={"title": "Budget dropped commitment", "status": "dropped"})

    resp = client.get("/api/register/picker?q=budget")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    titles = {i["title"] for i in items}
    assert "Budget closed item" not in titles
    assert "Budget dropped commitment" not in titles

    action_item = next(i for i in items if i["id"] == open_action["id"] and i["type"] == "action")
    assert action_item == {
        "type": "action",
        "id": open_action["id"],
        "title": "Budget review pack",
        "status": "todo",
        "due_date": "2026-09-01",
        "owner": {"id": priya["id"], "name": "Priya Shah"},
    }
    commitment_item = next(
        i for i in items if i["id"] == open_commitment["id"] and i["type"] == "commitment"
    )
    assert commitment_item["owner"] is None
    assert commitment_item["due_date"] is None

    # actions ordered before commitments
    types_in_order = [i["type"] for i in items]
    first_commitment_idx = types_in_order.index("commitment")
    assert all(t == "action" for t in types_in_order[:first_commitment_idx])
    assert all(t == "commitment" for t in types_in_order[first_commitment_idx:])


def test_register_picker_matches_owner_name(client):
    owner = client.post("/api/people", json={"name": "Zed Zephyr"}).json()
    action = client.post(
        "/api/actions", json={"title": "Totally unrelated title", "owner_id": owner["id"]}
    ).json()
    resp = client.get("/api/register/picker?q=Zephyr")
    ids = {i["id"] for i in resp.json()["items"] if i["type"] == "action"}
    assert action["id"] in ids


def test_register_picker_short_query_returns_empty(client):
    client.post("/api/actions", json={"title": "Anything"})
    assert client.get("/api/register/picker?q=a").json() == {"items": []}
    assert client.get("/api/register/picker").json() == {"items": []}


def test_register_picker_limit_clamped(client):
    for i in range(60):
        client.post("/api/actions", json={"title": f"Clamp target {i:02d}"})
    resp = client.get("/api/register/picker?q=Clamp&limit=1000")
    assert len(resp.json()["items"]) == 50

    resp_default = client.get("/api/register/picker?q=Clamp")
    assert len(resp_default.json()["items"]) == 20


def test_register_picker_reserves_commitment_slots(client):
    # 20+ matching actions used to saturate the default limit and make a
    # matching commitment unreachable in the results
    for i in range(30):
        client.post("/api/actions", json={"title": f"Reserve target {i:02d}"})
    commitment = client.post("/api/commitments", json={"title": "Reserve target commitment"}).json()

    resp = client.get("/api/register/picker?q=Reserve")
    items = resp.json()["items"]
    ids = {(i["type"], i["id"]) for i in items}
    assert ("commitment", commitment["id"]) in ids
    # actions still lead, commitments still trail, and title order holds
    # within each group
    types_in_order = [i["type"] for i in items]
    first_commitment_idx = types_in_order.index("commitment")
    assert all(t == "action" for t in types_in_order[:first_commitment_idx])
    assert all(t == "commitment" for t in types_in_order[first_commitment_idx:])
