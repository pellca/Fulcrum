"""Demo dataset — every row is flagged is_demo so it can be wiped without touching real data."""

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from ..models import (
    Action,
    Chase,
    Commitment,
    Decision,
    Forum,
    KeyDate,
    Link,
    Meeting,
    Person,
    Topic,
    Workstream,
)


def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def load_demo(db: Session) -> dict:
    today = date.today()

    people = {
        "principal": Person(name="Alex Morgan", role="Chief Audit Executive", team="IA&I", is_demo=True),
        "bpm1": Person(name="Priya Shah", role="Business Manager", team="IA&I COO", is_bpm=True, is_demo=True),
        "bpm2": Person(name="Tom Okafor", role="Business Manager", team="IA&I COO", is_bpm=True, is_demo=True),
        "dir_credit": Person(name="Sarah Chen", role="Audit Director", team="Credit & Markets", is_demo=True),
        "dir_fc": Person(name="James Whitfield", role="Audit Director", team="Financial Crime", is_demo=True),
        "dir_ops": Person(name="Lena Kovacs", role="Audit Director", team="Operations & Tech", is_demo=True),
        "reg": Person(name="Regulatory Liaison", role="Liaison", team="Compliance", is_demo=True),
    }
    db.add_all(people.values())
    db.flush()

    ws = {
        # sort_order drives the rolling agenda band order (and every other workstream
        # list), so the demo ships an order a chief of staff would actually pick:
        # the regulator-facing work first, discretionary improvement last.
        "s166": Workstream(name="S166 Response", category="governance", colour="#f59e0b", sort_order=1, owners=[people["dir_ops"], people["principal"]], is_demo=True),
        "aml": Workstream(name="AML Investigation", category="investigation", colour="#ef4444", sort_order=2, owners=[people["dir_fc"]], is_demo=True),
        "credit": Workstream(name="Credit Risk Audit", category="audit", colour="#6366f1", sort_order=3, owners=[people["dir_credit"]], is_demo=True),
        "method": Workstream(name="Methodology Refresh", category="initiative", colour="#10b981", sort_order=4, owners=[people["bpm1"], people["dir_ops"]], is_demo=True),
    }
    db.add_all(ws.values())
    db.flush()

    key_dates = [
        KeyDate(title="S166 skilled person report submission", date=today + timedelta(days=18), kind="regulator", hard=True, workstream_id=ws["s166"].id, is_demo=True),
        KeyDate(title="Audit Committee", date=today + timedelta(days=11), kind="board", hard=True, is_demo=True),
        KeyDate(title="AML case file handover to Legal", date=today + timedelta(days=25), kind="external_deadline", hard=True, workstream_id=ws["aml"].id, is_demo=True),
        KeyDate(title="Methodology pilot go/no-go", date=today + timedelta(days=32), kind="internal", workstream_id=ws["method"].id, is_demo=True),
    ]
    db.add_all(key_dates)
    db.flush()

    commitments = {
        "s166_draft": Commitment(
            title="Deliver S166 draft response pack to the regulator liaison",
            owner_id=people["dir_ops"].id, origin="external", origin_detail="PRA S166 review",
            workstream_id=ws["s166"].id, due_date=today + timedelta(days=14), status="at_risk",
            priority="high", is_demo=True,
        ),
        "credit_scope": Commitment(
            title="Agree revised credit risk audit scope with 2LoD",
            owner_id=people["dir_credit"].id, origin="aet", workstream_id=ws["credit"].id,
            due_date=today + timedelta(days=7), status="on_track", priority="high", is_demo=True,
        ),
        "aml_update": Commitment(
            title="Weekly AML investigation status note for the principal",
            owner_id=people["dir_fc"].id, origin="principal", workstream_id=ws["aml"].id,
            due_date=today + timedelta(days=2), status="open", priority="medium", is_demo=True,
        ),
        "method_pilot": Commitment(
            title="Complete methodology pilot on two live audits",
            owner_id=people["bpm1"].id, origin="aet", workstream_id=ws["method"].id,
            due_date=today + timedelta(days=30), status="on_track", priority="medium", is_demo=True,
        ),
        "overdue_mi": Commitment(
            title="Refresh AET MI pack format",
            owner_id=people["bpm2"].id, origin="principal", due_date=today - timedelta(days=5),
            status="open", priority="low", is_demo=True,
        ),
    }
    db.add_all(commitments.values())
    db.flush()

    actions = {
        "s166_evidence": Action(
            title="Collate evidence annexes for S166 pack", owner_id=people["dir_ops"].id,
            commitment_id=commitments["s166_draft"].id, workstream_id=ws["s166"].id,
            due_date=today + timedelta(days=5), status="blocked", priority="high",
            notes="Waiting on Ops data extract", is_demo=True,
        ),
        "s166_review": Action(
            title="Principal review of S166 pack", owner_id=people["principal"].id,
            commitment_id=commitments["s166_draft"].id, workstream_id=ws["s166"].id,
            due_date=today + timedelta(days=10), status="todo", priority="high", is_demo=True,
        ),
        "credit_2lod": Action(
            title="Book 2LoD scope walkthrough", owner_id=people["dir_credit"].id,
            commitment_id=commitments["credit_scope"].id, workstream_id=ws["credit"].id,
            due_date=today + timedelta(days=3), status="in_progress", priority="medium", is_demo=True,
        ),
        "aml_note": Action(
            title="Draft this week's AML status note", owner_id=people["dir_fc"].id,
            commitment_id=commitments["aml_update"].id, workstream_id=ws["aml"].id,
            due_date=today + timedelta(days=1), status="todo", priority="medium", is_demo=True,
        ),
        "mi_overdue": Action(
            title="Circulate draft MI pack for comment", owner_id=people["bpm2"].id,
            commitment_id=commitments["overdue_mi"].id,
            due_date=today - timedelta(days=3), status="todo", priority="low", is_demo=True,
        ),
        "method_training": Action(
            title="Schedule pilot team training session", owner_id=people["bpm1"].id,
            commitment_id=commitments["method_pilot"].id, workstream_id=ws["method"].id,
            due_date=today + timedelta(days=12), status="todo", priority="medium", is_demo=True,
        ),
    }
    db.add_all(actions.values())
    db.flush()

    db.add_all([
        Chase(action_id=actions["s166_evidence"].id, chased_on=today - timedelta(days=2), method="email",
              note="Chased Ops for the data extract", next_chase_on=today),
        Chase(action_id=actions["mi_overdue"].id, chased_on=today - timedelta(days=4), method="chat",
              note="Reminded Tom in Teams", next_chase_on=today - timedelta(days=1)),
        Chase(commitment_id=commitments["aml_update"].id, chased_on=today - timedelta(days=7), method="meeting",
              note="Raised in 1:1", next_chase_on=today + timedelta(days=7)),
    ])

    forums = {
        "aet": Forum(name="AET Weekly", chair_id=people["principal"].id, cadence="Weekly, Mondays 10:00",
                     capacity_minutes=60, audience="Audit Executive Team", colour="#0ea5e9", is_demo=True),
        "acprep": Forum(name="Audit Committee Prep", chair_id=people["principal"].id, cadence="Monthly",
                        capacity_minutes=90, audience="Principal + BPMs + presenting directors", colour="#8b5cf6", is_demo=True),
    }
    db.add_all(forums.values())
    db.flush()

    next_monday = _next_weekday(today + timedelta(days=1), 0)
    meetings = [
        Meeting(forum_id=forums["aet"].id, scheduled_at=datetime.combine(next_monday, time(10, 0)), is_demo=True),
        Meeting(forum_id=forums["aet"].id, scheduled_at=datetime.combine(next_monday + timedelta(days=7), time(10, 0)), is_demo=True),
        Meeting(forum_id=forums["acprep"].id, scheduled_at=datetime.combine(today + timedelta(days=8), time(14, 0)), is_demo=True),
    ]
    db.add_all(meetings)
    db.flush()

    topics = [
        Topic(title="S166 response: sign off key messages", intent="decide", duration_minutes=20,
              sponsors=[people["dir_ops"], people["principal"]], workstream_id=ws["s166"].id,
              commitment_id=commitments["s166_draft"].id, readiness="ready",
              target_by=today + timedelta(days=10), is_demo=True),
        Topic(title="Credit scope change: approve approach", intent="decide", duration_minutes=15,
              sponsors=[people["dir_credit"]], workstream_id=ws["credit"].id,
              commitment_id=commitments["credit_scope"].id, readiness="ready",
              target_by=today + timedelta(days=6), is_demo=True),
        Topic(title="AML investigation: status update", intent="inform", duration_minutes=10,
              sponsors=[people["dir_fc"]], workstream_id=ws["aml"].id, readiness="ready", is_demo=True),
        Topic(title="Methodology pilot: shape success criteria", intent="shape", duration_minutes=25,
              sponsors=[people["bpm1"], people["dir_credit"]], workstream_id=ws["method"].id, readiness="draft",
              target_by=today + timedelta(days=28), is_demo=True),
        Topic(title="2027 audit plan early look", intent="consult", duration_minutes=30,
              sponsors=[people["principal"]], status="parked", is_demo=True),
    ]
    db.add_all(topics)
    db.flush()

    db.add_all([
        Link(from_type="action", from_id=actions["s166_evidence"].id,
             to_type="action", to_id=actions["s166_review"].id, kind="blocks",
             rationale="Principal can't review until annexes are in"),
        Link(from_type="action", from_id=actions["s166_review"].id,
             to_type="commitment", to_id=commitments["s166_draft"].id, kind="precedes",
             rationale="Review gate before pack goes to liaison"),
        Link(from_type="commitment", from_id=commitments["credit_scope"].id,
             to_type="topic", to_id=topics[1].id, kind="informs"),
    ])

    decision = Decision(
        meeting_id=meetings[0].id, title="Adopt fortnightly S166 checkpoint",
        detail="Standing 15-min checkpoint until submission.", decided_on=today - timedelta(days=7),
        owner_id=people["principal"].id, review_on=today, is_demo=True,
    )
    db.add(decision)
    db.commit()

    return {
        "people": len(people), "workstreams": len(ws), "key_dates": len(key_dates),
        "commitments": len(commitments), "actions": len(actions), "topics": len(topics),
        "forums": len(forums), "meetings": len(meetings),
    }
