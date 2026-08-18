"""Forward-planner data: workstream lanes and dependency risk chains."""

from datetime import date

from sqlalchemy.orm import Session

from ..models import Action, Commitment, Decision, KeyDate, Link, MailMessage, Meeting, Topic, Workstream

DEPENDENCY_KINDS = ("blocks", "precedes")

TITLE_RESOLVERS = {
    "action": (Action, lambda r: r.title),
    "commitment": (Commitment, lambda r: r.title),
    "topic": (Topic, lambda r: r.title),
    "key_date": (KeyDate, lambda r: r.title),
    "workstream": (Workstream, lambda r: r.name),
    "decision": (Decision, lambda r: r.title),
    "meeting": (Meeting, lambda r: f"{r.forum.name} — {r.scheduled_at:%d %b %Y}"),
    "mail": (MailMessage, lambda r: r.subject or f"mail #{r.id}"),
}


def resolve_title(db: Session, entity_type: str, entity_id: int) -> str:
    entry = TITLE_RESOLVERS.get(entity_type)
    if not entry:
        return f"{entity_type} #{entity_id}"
    model, getter = entry
    row = db.get(model, entity_id)
    return getter(row) if row else f"{entity_type} #{entity_id} (deleted)"


def _troubled_items(db: Session, today: date) -> dict[tuple[str, int], str]:
    """Items that put their downstream dependants at risk, with the reason."""
    troubled: dict[tuple[str, int], str] = {}
    open_actions = db.query(Action).filter(Action.status.notin_(["done", "cancelled"]))
    for action in open_actions:
        if action.status == "blocked":
            troubled[("action", action.id)] = "blocked"
        elif action.due_date and action.due_date < today:
            troubled[("action", action.id)] = f"overdue since {action.due_date.isoformat()}"
    open_commitments = db.query(Commitment).filter(
        Commitment.status.notin_(["delivered", "dropped"])
    )
    for commitment in open_commitments:
        if commitment.status == "at_risk":
            troubled[("commitment", commitment.id)] = "at risk"
        elif commitment.due_date and commitment.due_date < today:
            troubled[("commitment", commitment.id)] = f"overdue since {commitment.due_date.isoformat()}"
    return troubled


def risk_chains(db: Session, today: date | None = None) -> list[dict]:
    """BFS downstream from troubled items over blocks/precedes edges."""
    today = today or date.today()
    troubled = _troubled_items(db, today)
    if not troubled:
        return []

    edges = db.query(Link).filter(Link.kind.in_(DEPENDENCY_KINDS)).all()
    downstream: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for edge in edges:
        downstream.setdefault((edge.from_type, edge.from_id), []).append(
            (edge.to_type, edge.to_id)
        )

    results = []
    for (src_type, src_id), reason in troubled.items():
        # walk everything downstream of this troubled item
        stack = [((src_type, src_id), [])]
        visited = {(src_type, src_id)}
        while stack:
            node, path = stack.pop()
            for child in downstream.get(node, []):
                if child in visited:
                    continue
                visited.add(child)
                chain = path + [node]
                results.append(
                    {
                        "item_type": child[0],
                        "item_id": child[1],
                        "item_title": resolve_title(db, *child),
                        "cause_type": src_type,
                        "cause_id": src_id,
                        "cause_title": resolve_title(db, src_type, src_id),
                        "cause_reason": reason,
                        "chain_length": len(chain),
                    }
                )
                stack.append((child, chain))
    results.sort(key=lambda r: (r["chain_length"], r["item_title"]))
    return results
