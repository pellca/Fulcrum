"""Chase queue: latest chase per item drives who needs nudging when."""

from datetime import date

from sqlalchemy.orm import Session

from ..models import Action, Chase, Commitment


def latest_chase_map(db: Session) -> dict[tuple[str, int], Chase]:
    """(type, id) -> most recent chase row."""
    latest: dict[tuple[str, int], Chase] = {}
    for chase in db.query(Chase).order_by(Chase.chased_on, Chase.id):
        if chase.action_id is not None:
            latest[("action", chase.action_id)] = chase
        elif chase.commitment_id is not None:
            latest[("commitment", chase.commitment_id)] = chase
    return latest


def next_chase_for(db: Session, kind: str, item_id: int) -> date | None:
    query = db.query(Chase)
    if kind == "action":
        query = query.filter(Chase.action_id == item_id)
    else:
        query = query.filter(Chase.commitment_id == item_id)
    row = query.order_by(Chase.chased_on.desc(), Chase.id.desc()).first()
    return row.next_chase_on if row else None


def chase_queue(db: Session, today: date | None = None) -> list[dict]:
    """Open items whose latest chase says re-chase on or before today."""
    today = today or date.today()
    latest = latest_chase_map(db)
    queue = []
    for (kind, item_id), chase in latest.items():
        if chase.next_chase_on is None or chase.next_chase_on > today:
            continue
        if kind == "action":
            item = db.get(Action, item_id)
            if item is None or item.status in ("done", "cancelled"):
                continue
            owner = item.owner.name if item.owner else None
            due = item.due_date
            title = item.title
        else:
            item = db.get(Commitment, item_id)
            if item is None or item.status in ("delivered", "dropped"):
                continue
            owner = item.owner.name if item.owner else None
            due = item.due_date
            title = item.title
        queue.append(
            {
                "item_type": kind,
                "item_id": item_id,
                "title": title,
                "owner_name": owner,
                "due_date": due.isoformat() if due else None,
                "last_chased_on": chase.chased_on.isoformat(),
                "next_chase_on": chase.next_chase_on.isoformat(),
                "days_overdue_chase": (today - chase.next_chase_on).days,
            }
        )
    queue.sort(key=lambda r: (-r["days_overdue_chase"], r["title"]))
    return queue
