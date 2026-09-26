from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.engine import manager
from app.db import get_db
from app.deps import get_current_user
from app.models import Bot, User, utcnow
from app.schemas import EngineIn

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"ok": True, "version": __version__}


def _system_view(db: Session, user: User) -> dict:
    now = utcnow()
    return {
        "engine_enabled": manager.engine_enabled(),
        "engine_started_at": manager.started_at.isoformat() if manager.started_at else None,
        "uptime_seconds": (now - manager.started_at).total_seconds() if manager.started_at else 0,
        "running_bots": sum(1 for bot_id in db.scalars(select(Bot.id).where(Bot.user_id == user.id)) if manager.is_running(bot_id)),
        "total_bots": db.scalar(select(func.count(Bot.id)).where(Bot.user_id == user.id)) or 0,
        "server_time": now.isoformat(),
        "version": __version__,
    }


@router.get("/system")
def system(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _system_view(db, user)


@router.post("/system/engine")
def set_engine(body: EngineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    manager.set_engine(body.enabled)
    return _system_view(db, user)
