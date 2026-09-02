"""The one discussion-point list builder. Dashboard, the 1:1 pack and the
GET /discussion-points endpoint all call this, so ordering and shape cannot
drift between the three surfaces that show the same list."""

from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from ..models import DiscussionPoint, Link
from .timeline import TITLE_RESOLVERS


def discussion_list(db: Session, person_id: int, include_closed: bool = False) -> list[dict]:
    """Never-discussed first, then stalest — so a standing item that keeps
    getting covered sinks down the list while anything new or overdue floats
    to the top."""
    priority_rank = case(
        (DiscussionPoint.priority == "high", 0),
        (DiscussionPoint.priority == "medium", 1),
        (DiscussionPoint.priority == "low", 2),
        else_=99,
    )
    query = db.query(DiscussionPoint).filter(DiscussionPoint.person_id == person_id)
    if not include_closed:
        query = query.filter(DiscussionPoint.status == "open")
    points = query.order_by(
        DiscussionPoint.last_discussed_on.isnot(None),
        DiscussionPoint.last_discussed_on.asc(),
        priority_rank,
        DiscussionPoint.raised_on.asc(),
    ).all()
    if not points:
        return []

    # one query for the links, then at most one per referenced entity type —
    # never a query per point, let alone per link. discussion_point is a
    # LINKABLE type like any other, so a link can just as well have been
    # created the other way round (e.g. from an action *to* a point) — match
    # on either end and normalise to "the other side" below.
    point_ids = [p.id for p in points]
    links = (
        db.query(Link)
        .filter(
            or_(
                (Link.from_type == "discussion_point") & (Link.from_id.in_(point_ids)),
                (Link.to_type == "discussion_point") & (Link.to_id.in_(point_ids)),
            )
        )
        .all()
    )

    def _other_side(link: Link) -> tuple[int, str, int]:
        """(point_id, other_type, other_id) regardless of which end the point is on."""
        if link.from_type == "discussion_point" and link.from_id in set(point_ids):
            return link.from_id, link.to_type, link.to_id
        return link.to_id, link.from_type, link.from_id

    ids_by_type: dict[str, set[int]] = {}
    for link in links:
        _, other_type, other_id = _other_side(link)
        ids_by_type.setdefault(other_type, set()).add(other_id)

    titles: dict[tuple[str, int], str] = {}
    for entity_type, ids in ids_by_type.items():
        entry = TITLE_RESOLVERS.get(entity_type)
        if not entry:
            continue
        model, getter = entry
        for row in db.query(model).filter(model.id.in_(ids)).all():
            titles[(entity_type, row.id)] = getter(row)

    links_by_point: dict[int, list[dict]] = {}
    for link in links:
        point_id, other_type, other_id = _other_side(link)
        title = titles.get((other_type, other_id))
        if title is None:
            continue  # target deleted; prune_links catches up on its own delete path
        links_by_point.setdefault(point_id, []).append(
            {"type": other_type, "id": other_id, "title": title}
        )

    return [
        {
            "id": p.id,
            "person_id": p.person_id,
            "title": p.title,
            "detail": p.detail,
            "priority": p.priority,
            "status": p.status,
            "raised_on": p.raised_on,
            "last_discussed_on": p.last_discussed_on,
            "times_discussed": p.times_discussed,
            "closed_on": p.closed_on,
            "outcome": p.outcome,
            "links": links_by_point.get(p.id, []),
        }
        for p in points
    ]
