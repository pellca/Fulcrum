from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.copilot_prompt import build_prompt
from ..services.people_import import commit_people, preview_people
from ..services.planner_import import (
    TEMPLATES,
    commit_import,
    preview_import,
    rows_from_csv,
    rows_from_xlsx,
    template_csv,
)

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/planner/preview")
async def planner_preview(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        rows = rows_from_xlsx(content) if name.endswith((".xlsx", ".xlsm")) else rows_from_csv(content)
        return preview_import(db, rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Could not read file: {exc}")


class CommitIn(BaseModel):
    items: list[dict]
    default_meeting_id: int | None = None


@router.post("/planner/commit")
def planner_commit(body: CommitIn, db: Session = Depends(get_db)):
    created = commit_import(db, body.items, body.default_meeting_id)
    return {"created": created}


@router.get("/copilot-prompt", response_class=PlainTextResponse)
def copilot_prompt(db: Session = Depends(get_db)):
    return build_prompt(db)


@router.post("/people/preview")
async def people_preview(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        rows = rows_from_xlsx(content) if name.endswith((".xlsx", ".xlsm")) else rows_from_csv(content)
        return preview_people(db, rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Could not read file: {exc}")


class PeopleCommitIn(BaseModel):
    items: list[dict]


@router.post("/people/commit")
def people_commit(body: PeopleCommitIn, db: Session = Depends(get_db)):
    return commit_people(db, body.items)


@router.get("/templates/{name}", response_class=PlainTextResponse)
def get_template(name: str):
    if name not in TEMPLATES:
        raise HTTPException(404, f"No template '{name}'. Available: {', '.join(TEMPLATES)}")
    return PlainTextResponse(
        template_csv(name),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}-template.csv"'},
    )
