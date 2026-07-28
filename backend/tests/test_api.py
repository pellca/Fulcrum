def test_full_lifecycle(client):
    # seed demo data
    seeded = client.post("/api/admin/seed").json()
    assert seeded["commitments"] >= 4

    # dashboard aggregates
    summary = client.get("/api/dashboard/summary").json()
    assert summary["chase_queue"], "seed should produce chases due"
    assert summary["meetings"], "seed should produce upcoming meetings"

    # agenda flow: candidates -> add top candidate -> capacity respected in payload
    meeting_id = summary["meetings"][0]["id"]
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
    assert result["created"] == {"actions": 1, "commitments": 1, "meeting_links": 2}

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
