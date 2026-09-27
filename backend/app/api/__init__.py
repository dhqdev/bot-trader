from fastapi import APIRouter

from app.api import ai, auth, autopilot, bots, dashboard, market, news, robots, security, settings, strategies, system

api_router = APIRouter(prefix="/api")
for module in (auth, security, settings, system, market, strategies, bots, robots, dashboard, ai, autopilot, news):
    api_router.include_router(module.router)
