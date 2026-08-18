from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .config import APP_NAME, FRONTEND_DIST
from .db import init_db

app = FastAPI(title=APP_NAME, docs_url="/api/docs", openapi_url="/api/openapi.json")
init_db()
app.include_router(api_router)


# keep unknown /api paths out of the SPA catch-all below — without this, a GET
# serves index.html and any other method gets a misleading 405 from Starlette
@app.api_route(
    "/api/{rest:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def unknown_api_route(rest: str):
    raise HTTPException(
        404,
        f"No API route matches this method and path (/api/{rest}). Check the method — "
        "or if Fulcrum was just updated, restart the server.",
    )

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
