"""Generate the Teams Copilot extraction prompt, personalised with live Fulcrum data
(known people, workstreams and forums) so Copilot's output lands cleanly on import."""

from datetime import date

from sqlalchemy.orm import Session

from ..models import Forum, Person, Workstream

CSV_HEADER = "type,title,description,owner,workstream,due,priority,origin,meeting"


def build_prompt(db: Session) -> str:
    people = db.query(Person).filter(Person.active.is_(True)).order_by(Person.name).all()
    workstreams = (
        db.query(Workstream).filter(Workstream.status == "active").order_by(Workstream.name).all()
    )
    forums = db.query(Forum).order_by(Forum.name).all()

    people_list = ", ".join(p.name for p in people) or "(none registered yet)"
    ws_list = ", ".join(w.name for w in workstreams) or "(none registered yet)"
    forum_list = ", ".join(f.name for f in forums) or "(none registered yet)"
    today = date.today().isoformat()

    return f"""Review this meeting's transcript and chat in full, then extract every action and commitment into a single CSV code block. Output ONLY the CSV — no commentary before or after.

Use exactly this header row:
{CSV_HEADER}

One row per item. Rules for each column:

- **type**: `action` for a concrete task someone must do; `commitment` for a promise to deliver something to a senior stakeholder, the executive team, or an external party (a commitment is usually bigger than a task and may spawn several actions).
- **title**: imperative, specific, max 120 characters (e.g. "Circulate revised scope paper to 2LoD"). Never vague ("follow up", "discuss further") — say what, to/with whom.
- **description**: one sentence of context — who raised it, what prompted it, and any conditions agreed. Wrap in double quotes if it contains commas.
- **owner**: the full name of the person who accepted or was assigned the item. Match to one of these known people where possible, using exactly this spelling: {people_list}. If the owner is someone else, give their name as stated in the meeting. If genuinely unassigned, leave blank.
- **workstream**: the most relevant of these, exactly as written, or blank if none clearly applies: {ws_list}.
- **due**: date in YYYY-MM-DD. Resolve relative phrases from the meeting date (today is {today}): "by Friday", "end of month", "before the committee". If no timeframe was stated or implied, leave blank — do not invent one.
- **priority**: `high`, `medium`, or `low`, judged from the conversation, not defaults. Signals for high: the most senior person in the meeting asked for it personally; a regulator, auditor, board or committee deadline depends on it; it blocks other work discussed; it was raised repeatedly or with urgency/frustration. Signals for low: nice-to-have, "when you get a chance", no dependency. Otherwise medium.
- **origin** (commitments only, leave blank for actions): `principal` if requested by the function head/chair personally; `aet` if agreed collectively by the executive team; `external` if owed to a regulator, auditor or party outside the function; `self` if volunteered.
- **meeting**: this meeting's governance forum name if it matches one of: {forum_list} — followed by the meeting date, e.g. "AET Weekly {today}". Leave blank if this meeting is none of those forums.

Quality bar:
- Extract only items genuinely agreed or assigned — not ideas that were merely floated and dropped.
- If the same item was restated several times, output it once with the final agreed owner and date.
- Where a decision created follow-up work, capture the follow-up work as rows (the decision itself is not a row).
- Do not fabricate owners, dates or priorities; blank is better than guessed.
"""
