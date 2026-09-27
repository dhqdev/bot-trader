"""Notícias do mercado, índice de medo e ganância e travas ativas nos bots."""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core import newsguard
from app.core.risk import RiskConfig
from app.core.sentiment import FILTER_LABELS, live_check, sentiment
from app.db import get_db
from app.deps import get_current_user
from app.models import Bot, User
from app.services import news

router = APIRouter(prefix="/news", tags=["news"])

_last_refresh = 0.0


@router.get("")
def list_news(
    asset: str | None = Query(None, max_length=16),
    impact: str | None = Query(None, pattern="^(low|medium|high)$"),
    hours: int = Query(72, ge=1, le=720),
    limit: int = Query(100, ge=1, le=300),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return news.list_news(db, asset, impact, hours, limit)


@router.get("/sentiment")
def market_sentiment(days: int = Query(120, ge=7, le=1000), _: User = Depends(get_current_user)):
    return {"latest": sentiment.latest(), "history": sentiment.history(days), "filters": FILTER_LABELS}


@router.get("/status")
def news_status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return news.status(db)


@router.get("/alerts")
def alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Para cada bot: se o sentimento ou uma notícia estão bloqueando compras agora."""
    out = []
    for bot in db.scalars(select(Bot).where(Bot.user_id == user.id).order_by(Bot.id)):
        risk = RiskConfig(**(bot.risk or {}))
        ok, reason, _ = live_check(risk.sentiment_filter, risk.fear_threshold)
        item = newsguard.entry_block(db, bot.base_asset, risk.news_guard, risk.news_window_hours)
        if item is not None and ok:
            ok, reason = False, f"notícia negativa de alto impacto: {newsguard.describe(item)}"
        out.append(
            {
                "bot_id": bot.id,
                "name": bot.name,
                "symbol": bot.symbol,
                "asset": bot.base_asset,
                "status": bot.status,
                "blocked": not ok,
                "reason": reason,
                "news": news.news_view(item) if item is not None else None,
                "sentiment_filter": risk.sentiment_filter,
                "news_guard": risk.news_guard,
            }
        )
    return out


@router.post("/refresh")
async def refresh(_: User = Depends(get_current_user)):
    """Busca notícias e o índice agora (no máximo uma vez por minuto)."""
    global _last_refresh
    if time.monotonic() - _last_refresh < 60:
        raise HTTPException(429, "Atualizado há menos de 1 minuto. Aguarde um pouco.")
    _last_refresh = time.monotonic()

    def work() -> dict:
        result = news.collect()
        try:
            sentiment.refresh()
        except Exception as exc:
            result["errors"]["Medo e ganância"] = str(exc)[:200]
        return result

    return await run_in_threadpool(work)
