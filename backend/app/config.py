import os
from pathlib import Path

APP_NAME = "Fulcrum"
APP_TAGLINE = "Chief of Staff operating platform"
PORT = int(os.environ.get("FULCRUM_PORT", "8742"))

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
IMPORTS_DIR = DATA_DIR / "imports"
DB_PATH = Path(os.environ.get("FULCRUM_DB", DATA_DIR / "fulcrum.db"))
MODULES_REGISTRY_DIR = REPO_ROOT / "modules" / "registry"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
