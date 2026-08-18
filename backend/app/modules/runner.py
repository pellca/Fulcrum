"""Module launcher: manifest registry + subprocess runner with captured logs.

A manifest (modules/registry/<name>.json) looks like:
{
  "name": "diary-import",
  "label": "Diary import",
  "description": "Ingest a diary.json produced by the Outlook Diary Extractor",
  "platform": "any",              // any | windows | linux
  "builtin": "diary_import",      // handled in-process, OR:
  "command": ["python", "script.py", "--flag", "{argname}"],
  "cwd": "/path/to/tool",
  "args": [{"name": "path", "label": "diary.json path", "required": true, "default": ""}],
  "ingest": "diary"               // auto-import the artifact after a command run
}
"""

import json
import platform
import shlex
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..config import MODULES_REGISTRY_DIR
from ..db import SessionLocal
from ..models import ModuleRun


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load_registry() -> list[dict]:
    manifests = []
    for path in sorted(MODULES_REGISTRY_DIR.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest.setdefault("name", path.stem)
            manifest.setdefault("platform", "any")
            manifest.setdefault("args", [])
            manifest["available"] = manifest["platform"] in ("any", platform.system().lower())
            manifests.append(manifest)
        except (json.JSONDecodeError, OSError) as exc:
            manifests.append({"name": path.stem, "error": str(exc), "available": False, "args": []})
    return manifests


def get_manifest(name: str) -> dict | None:
    return next((m for m in load_registry() if m.get("name") == name), None)


def start_run(manifest: dict, args: dict[str, str]) -> int:
    """Create the ModuleRun row and kick off execution in a worker thread."""
    db = SessionLocal()
    try:
        run = ModuleRun(
            module_name=manifest["name"],
            started_at=_now(),
            status="running",
            args=json.dumps(args),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    finally:
        db.close()

    thread = threading.Thread(
        target=_execute, args=(manifest, args, run_id), daemon=True, name=f"module-{run_id}"
    )
    thread.start()
    return run_id


def _finish(run_id: int, status: str, log_suffix: str = "", artifact: str | None = None) -> None:
    db = SessionLocal()
    try:
        run = db.get(ModuleRun, run_id)
        if run:
            run.status = status
            run.finished_at = _now()
            if log_suffix:
                run.log = (run.log or "") + log_suffix
            if artifact:
                run.artifact_path = artifact
            db.commit()
    finally:
        db.close()


def _append_log(run_id: int, text: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(ModuleRun, run_id)
        if run:
            run.log = (run.log or "") + text
            db.commit()
    finally:
        db.close()


def _execute(manifest: dict, args: dict[str, str], run_id: int) -> None:
    try:
        if manifest.get("builtin"):
            _run_builtin(manifest, args, run_id)
        else:
            _run_command(manifest, args, run_id)
    except Exception as exc:  # a module crashing must never take the app down
        _finish(run_id, "failed", f"\n[runner] {type(exc).__name__}: {exc}\n")


def _run_builtin(manifest: dict, args: dict[str, str], run_id: int) -> None:
    name = manifest["builtin"]
    if name == "diary_import":
        from ..services.diary_import import import_diary_file

        path = args.get("path", "")
        db = SessionLocal()
        try:
            summary = import_diary_file(db, path)
        finally:
            db.close()
        pretty = json.dumps(summary, indent=2)
        _finish(run_id, "succeeded", f"Imported {path}\n{pretty}\n", artifact=path)
    else:
        raise ValueError(f"Unknown builtin '{name}'")


def _run_command(manifest: dict, args: dict[str, str], run_id: int) -> None:
    command = [part.format(**args) for part in manifest["command"]]
    cwd = manifest.get("cwd") or None
    _append_log(run_id, f"$ {shlex.join(command)}\n")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    buffer: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        buffer.append(line)
        if len(buffer) >= 10:
            _append_log(run_id, "".join(buffer))
            buffer.clear()
    process.wait()
    if buffer:
        _append_log(run_id, "".join(buffer))

    artifact = manifest.get("artifact", "")
    artifact = artifact.format(**args) if artifact else None
    status = "succeeded" if process.returncode == 0 else "failed"
    _finish(run_id, status, f"\n[exit code {process.returncode}]\n", artifact=artifact)

    ingest = manifest.get("ingest")
    if status == "succeeded" and ingest == "diary" and artifact:
        from ..services.diary_import import import_diary_file

        db = SessionLocal()
        try:
            summary = import_diary_file(db, artifact)
            _append_log(run_id, "[ingest] " + json.dumps(summary) + "\n")
        except Exception as exc:
            _append_log(run_id, f"[ingest failed] {exc}\n")
        finally:
            db.close()
    elif status == "succeeded" and ingest == "mail" and artifact:
        from ..services.mail_import import import_mail_file

        db = SessionLocal()
        try:
            summary = import_mail_file(db, artifact)
            _append_log(run_id, "[ingest] " + json.dumps(summary) + "\n")
        except Exception as exc:
            _append_log(run_id, f"[ingest failed] {exc}\n")
        finally:
            db.close()
