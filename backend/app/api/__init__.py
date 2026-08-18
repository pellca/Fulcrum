from fastapi import APIRouter

from . import (
    admin,
    bulk,
    dashboard,
    diary,
    imports,
    links,
    mail,
    meetings,
    modules_api,
    people,
    planner,
    register,
    search,
    workstreams,
)

api_router = APIRouter(prefix="/api")
for module in (
    people, workstreams, register, links, meetings, planner, diary,
    mail, modules_api, imports, admin, dashboard, search, bulk,
):
    api_router.include_router(module.router)
