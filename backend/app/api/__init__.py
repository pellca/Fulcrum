from fastapi import APIRouter

from . import admin, dashboard, diary, imports, links, meetings, modules_api, people, planner, register, search, workstreams

api_router = APIRouter(prefix="/api")
for module in (people, workstreams, register, links, meetings, planner, diary, modules_api, imports, admin, dashboard, search):
    api_router.include_router(module.router)
