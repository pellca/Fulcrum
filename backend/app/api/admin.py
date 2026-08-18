import json
import time
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ..config import DATA_DIR, DB_PATH
from ..db import Base, engine, get_db
from ..models import DiaryEvent, Link, MailMessage, Meeting, ModuleRun
from ..schemas import ClearIn
from ..services.seed import load_demo
from ..services.timeline import TITLE_RESOLVERS

router = APIRouter(prefix="/admin", tags=["admin"])

DEMO_TABLES = [
    "chase",
    "agenda_item",
    "decision",
    "topic",
    "meeting",
    "forum",
    "action",
    "commitment",
    "key_date",
    "workstream",
    "person_note",
    "person",
]


@router.get("/backup")
def backup_db():
    """Consistent snapshot of the SQLite file (safe under WAL)."""
    snapshot = DATA_DIR / f"fulcrum-backup-{int(time.time())}.db"
    with engine.connect() as connection:
        connection.exec_driver_sql(f"VACUUM INTO '{snapshot}'")
    return FileResponse(
        snapshot,
        media_type="application/octet-stream",
        filename=f"fulcrum-{date.today().isoformat()}.db",
    )


@router.get("/export.json")
def export_json(db: Session = Depends(get_db)):
    def encode(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    dump = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(table.select()).mappings().all()
        dump[table.name] = [{k: encode(v) for k, v in row.items()} for row in rows]
    return JSONResponse(
        dump,
        headers={
            "Content-Disposition": f'attachment; filename="fulcrum-{date.today().isoformat()}.json"'
        },
    )


def _prune_orphan_links(db: Session) -> None:
    for link in db.query(Link).all():
        for entity_type, entity_id in ((link.from_type, link.from_id), (link.to_type, link.to_id)):
            entry = TITLE_RESOLVERS.get(entity_type)
            if entry and db.get(entry[0], entity_id) is None:
                db.delete(link)
                break


@router.post("/clear")
def clear_data(body: ClearIn, db: Session = Depends(get_db)):
    if body.confirm != "CLEAR":
        raise HTTPException(422, 'Type "CLEAR" to confirm')

    if body.scope == "all":
        db.close()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return {"cleared": "all"}

    if body.scope == "demo":
        deleted = 0
        for table_name in DEMO_TABLES:
            table = Base.metadata.tables[table_name]
            if "is_demo" in table.c:
                result = db.execute(table.delete().where(table.c.is_demo.is_(True)))
            else:
                # chase/agenda rows attached to demo parents die via FK cascade;
                # anything left pointing nowhere is handled below
                continue
            deleted += result.rowcount or 0
        _prune_orphan_links(db)
        db.commit()
        return {"cleared": "demo", "rows": deleted}

    if body.scope == "diary":
        db.query(Meeting).filter(Meeting.diary_event_id.isnot(None)).update(
            {"diary_event_id": None}, synchronize_session=False
        )
        deleted = db.query(DiaryEvent).delete()
        db.commit()
        return {"cleared": "diary", "rows": deleted}

    if body.scope == "mail":
        deleted = db.query(MailMessage).delete()
        db.query(Link).filter(or_(Link.from_type == "mail", Link.to_type == "mail")).delete(
            synchronize_session=False
        )
        db.commit()
        return {"cleared": "mail", "rows": deleted}

    if body.scope == "module_runs":
        deleted = db.query(ModuleRun).delete()
        db.commit()
        return {"cleared": "module_runs", "rows": deleted}

    raise HTTPException(422, "Unknown scope")


@router.post("/seed")
def seed_demo(db: Session = Depends(get_db)):
    return load_demo(db)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    counts = {}
    for table in Base.metadata.sorted_tables:
        counts[table.name] = db.execute(
            text(f"SELECT COUNT(*) FROM {table.name}")
        ).scalar()
    return counts
