from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ModuleRun
from ..modules.runner import get_manifest, load_registry, start_run
from ..schemas import ModuleRunOut

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("")
def list_modules():
    return load_registry()


class RunIn(BaseModel):
    args: dict[str, str] = {}


@router.post("/{name}/run")
def run_module(name: str, body: RunIn):
    manifest = get_manifest(name)
    if not manifest:
        raise HTTPException(404, f"No module '{name}'")
    if manifest.get("error"):
        raise HTTPException(422, f"Manifest error: {manifest['error']}")
    if not manifest.get("available", False):
        raise HTTPException(
            409, f"Module '{name}' requires platform '{manifest.get('platform')}'"
        )
    missing = [
        arg["name"]
        for arg in manifest.get("args", [])
        if arg.get("required") and not body.args.get(arg["name"])
    ]
    if missing:
        raise HTTPException(422, f"Missing required args: {', '.join(missing)}")
    run_id = start_run(manifest, body.args)
    return {"run_id": run_id}


@router.get("/runs", response_model=list[ModuleRunOut])
def list_runs(limit: int = 30, db: Session = Depends(get_db)):
    return db.query(ModuleRun).order_by(ModuleRun.id.desc()).limit(limit).all()


@router.get("/runs/{run_id}", response_model=ModuleRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ModuleRun, run_id)
    if not run:
        raise HTTPException(404)
    return run
