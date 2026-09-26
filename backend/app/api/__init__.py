from fastapi import APIRouter

from app.api import ai, auth, bots, dashboard, market, settings, strategies, system

api_router = APIRouter(prefix="/api")
for module in (auth, settings, system, market, strategies, bots, dashboard, ai):
    api_router.include_router(module.router)
