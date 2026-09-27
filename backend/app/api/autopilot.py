"""Piloto automático: configuração por bot, ciclos de otimização e base de conhecimento."""

import threading
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.account import audit, require_step_up
from app.db import get_db
from app.deps import get_current_user, get_user_bot
from app.models import AIInsight, Bot, OptimizationRun, User, utcnow
from app.schemas import StepUpIn
from app.services import optimizer
from app.services.ai import resolve_api_key

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


class AutopilotIn(StepUpIn):
    mode: Literal["off", "suggest", "auto_paper", "auto_all"]
    interval_hours: int = Field(168, ge=6, le=24 * 30)
    allow_strategy_change: bool = True


def launch(run_id: int, api_key: str | None) -> None:
    """Roda o ciclo em segundo plano (os testes trocam por execução direta)."""
    threading.Thread(target=optimizer.execute, args=(run_id, api_key), daemon=True, name=f"optimize-{run_id}").start()


def _bot_brief(bot: Bot) -> dict:
    return {"id": bot.id, "name": bot.name, "symbol": bot.symbol, "interval": bot.interval, "mode": bot.mode, "status": bot.status, "strategy": bot.strategy}


def _latest(db: Session, bot_id: int, *statuses: str) -> OptimizationRun | None:
    q = select(OptimizationRun).where(OptimizationRun.bot_id == bot_id)
    if statuses:
        q = q.where(OptimizationRun.status.in_(statuses))
    return db.scalar(q.order_by(OptimizationRun.id.desc()))


def _own_run(run_id: int, user: User, db: Session) -> OptimizationRun:
    run = db.get(OptimizationRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "Ciclo não encontrado")
    return run


@router.get("")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = []
    for bot in db.scalars(select(Bot).where(Bot.user_id == user.id).order_by(Bot.id)):
        cfg = optimizer.get_autopilot(db, bot)
        last = _latest(db, bot.id)
        suggestion = _latest(db, bot.id, "suggested")
        applied = _latest(db, bot.id, "applied")
        items.append(
            {
                "bot": _bot_brief(bot),
                "autopilot": optimizer.autopilot_view(cfg),
                "running": optimizer.is_running(db, bot.id),
                "last_run": optimizer.run_view(last) if last else None,
                "suggestion": optimizer.run_view(suggestion) if suggestion else None,
                "last_applied": {**optimizer.run_view(applied), "followup": optimizer.followup(db, applied)} if applied else None,
            }
        )
    db.commit()
    return {"bots": items, "ai_configured": bool(resolve_api_key(user.id)), "modes": optimizer.MODE_LABELS}


@router.get("/bots/{bot_id}")
def bot_autopilot(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    cfg = optimizer.get_autopilot(db, bot)
    suggestion = _latest(db, bot.id, "suggested")
    last = _latest(db, bot.id)
    db.commit()
    return {
        "autopilot": optimizer.autopilot_view(cfg),
        "running": optimizer.is_running(db, bot.id),
        "last_run": optimizer.run_view(last) if last else None,
        "suggestion": optimizer.run_view(suggestion) if suggestion else None,
    }


@router.put("/bots/{bot_id}")
def update_autopilot(body: AutopilotIn, request: Request, bot: Bot = Depends(get_user_bot), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = optimizer.get_autopilot(db, bot)
    if body.mode == "auto_all" and cfg.live_authorized_at is None:
        # mexer sozinho em bot com dinheiro real exige confirmar a senha (e o 2FA)
        require_step_up(db, user, body.password, body.code, request, "piloto automático em bots reais")
        cfg.live_authorized_at = utcnow()
        audit(db, user.id, "autopilot_live", request, bot.name)
    if body.mode != "auto_all":
        cfg.live_authorized_at = None
    was_off = cfg.mode == "off"
    cfg.mode = body.mode
    cfg.interval_hours = body.interval_hours
    cfg.allow_strategy_change = body.allow_strategy_change
    if was_off and body.mode != "off":
        cfg.next_run_at = utcnow() + timedelta(minutes=10)
    elif cfg.last_run_at is not None:
        cfg.next_run_at = cfg.last_run_at + timedelta(hours=body.interval_hours)
    db.commit()
    return optimizer.autopilot_view(cfg)


@router.post("/bots/{bot_id}/run")
def run_now(bot: Bot = Depends(get_user_bot), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if optimizer.is_running(db, bot.id):
        raise HTTPException(409, "Já há uma otimização rodando para este bot.")
    optimizer.get_autopilot(db, bot)
    run = optimizer.start_run(db, bot, "manual")
    db.commit()
    launch(run.id, resolve_api_key(user.id))
    return optimizer.run_view(run)


@router.get("/runs")
def list_runs(bot_id: int | None = None, limit: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(OptimizationRun).where(OptimizationRun.user_id == user.id)
    if bot_id is not None:
        q = q.where(OptimizationRun.bot_id == bot_id)
    return [optimizer.run_view(r) for r in db.scalars(q.order_by(OptimizationRun.id.desc()).limit(limit))]


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(run_id, user, db)
    return {**optimizer.run_view(run, full=True), "followup": optimizer.followup(db, run)}


@router.post("/runs/{run_id}/apply")
def apply(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(run_id, user, db)
    if run.status != "suggested":
        raise HTTPException(400, "Só dá para aplicar uma sugestão pendente.")
    try:
        optimizer.apply_run(db, run, actor="user")
        optimizer._supersede_older(db, run)
        db.commit()
    except optimizer.ApplyError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return optimizer.run_view(run)


@router.post("/runs/{run_id}/reject")
def reject(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(run_id, user, db)
    if run.status != "suggested":
        raise HTTPException(400, "Só dá para recusar uma sugestão pendente.")
    run.status = "rejected"
    db.commit()
    return optimizer.run_view(run)


@router.post("/runs/{run_id}/revert")
def revert(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(run_id, user, db)
    try:
        optimizer.revert_run(db, run)
        db.commit()
    except optimizer.ApplyError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return optimizer.run_view(run)


@router.get("/insights")
def insights(symbol: str | None = Query(None, max_length=32), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AIInsight).where(AIInsight.user_id == user.id, AIInsight.active.is_(True))
    if symbol:
        q = q.where(AIInsight.symbol == symbol.upper())
    return [optimizer.insight_view(i) for i in db.scalars(q.order_by(AIInsight.id.desc()).limit(100))]


@router.delete("/insights/{insight_id}")
def forget(insight_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(AIInsight, insight_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Lição não encontrada")
    item.active = False
    db.commit()
    return {"ok": True}
