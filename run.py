#!/usr/bin/env python3
"""Launch Fulcrum: serve the built frontend + API on one port and open the browser."""

import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import APP_NAME, FRONTEND_DIST, PORT  # noqa: E402


def main() -> None:
    if not (FRONTEND_DIST / "index.html").exists():
        print(f"[{APP_NAME}] frontend/dist not found — build it once with:")
        print("    cd frontend && npm install && npm run build")
        print(f"[{APP_NAME}] starting API only (docs at http://localhost:{PORT}/api/docs)")
    else:
        threading.Timer(1.2, webbrowser.open, args=(f"http://localhost:{PORT}",)).start()

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
