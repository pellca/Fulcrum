"""Shared helpers for the JSON file importers (diary_import, mail_import).

Both importers upsert by a caller-supplied primary key while running under a
session with autoflush disabled (see app/db.py). A newly db.add()'ed row with a
manually-assigned PK does not enter the session's identity map until flushed,
so db.get()/query().first() cannot see it — if the same id appears twice in one
input file, both occurrences look "new" and the single flush at the end of the
loop hits a primary-key collision. De-duplicating the input list up front, before
the add/update loop runs, avoids that class of bug entirely.
"""


def dedupe_by_id(items: list[dict], key: str = "id") -> tuple[list[dict], int]:
    """Collapse `items` to one entry per value of `key`, last occurrence wins.

    Entries with a missing/falsy key are left in place untouched (and are not
    counted as duplicates) — callers already have their own "skip" behaviour
    for those. Returns the de-duplicated list (relative order of the surviving
    entries preserved) and the count of entries dropped as duplicates.

    Last-wins here is a deliberate divergence from `tools/mail_extractor/mail_normalize.py`'s
    `dedupe_messages()`, which is first-wins. That's correct for the extractor: it de-dupes
    *within a single run* of the same source query, where a repeated id is an artefact of the
    query overlapping itself and every copy carries identical content, so which one survives
    doesn't matter. This function instead de-dupes a full-window re-export handed to the
    importer, where two entries sharing an id can legitimately carry *different* content (e.g.
    a row edited and re-emitted later in the same file) — the later entry is the more recently
    written record, so it should be the one that lands in the DB.
    """
    last_index: dict = {}
    for index, item in enumerate(items):
        value = item.get(key) if isinstance(item, dict) else None
        # An id must be a hashable, sensible scalar (str/int) to key a dict by. A
        # malformed input can carry a list/dict in the id field; treat that the
        # same as a missing id (left in place, not counted as a duplicate) rather
        # than crashing on an unhashable dict key.
        if not value or not isinstance(value, (str, int)):
            continue
        last_index[value] = index

    duplicates = 0
    deduped: list[dict] = []
    for index, item in enumerate(items):
        value = item.get(key) if isinstance(item, dict) else None
        if not value or not isinstance(value, (str, int)):
            deduped.append(item)
            continue
        if last_index[value] != index:
            duplicates += 1
            continue
        deduped.append(item)
    return deduped, duplicates
