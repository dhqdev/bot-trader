"""Modo automático: um botão e a IA faz o resto (escolhe, testa, liga, acompanha e troca os robôs)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy.orm import Session

from app.account import audit, require_step_up
from app.core.engine import okx_credential
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import StepUpIn
from app.services import autotrade
from app.services.llm import resolve_ai

router = APIRouter(prefix="/auto", tags=["auto"])


class StartIn(StepUpIn):
    mode: Literal["paper", "live"] = "paper"
    budget: float | None = Field(None, ge=autotrade.MIN_PER_ROBOT, le=10_000_000)


def _launch(db: Session, user_id: int, trigger: str) -> None:
    if autotrade.is_running(db, user_id):
        db.commit()
        return  # o ciclo em andamento termina e o agendador roda o próximo na hora marcada
    cycle = autotrade.start_cycle(db, user_id, trigger)
    db.commit()
    autotrade.launch(cycle.id, resolve_ai(user_id))
    db.expire_all()  # a resposta mostra o que o ciclo já tiver mudado


@router.get("")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = autotrade.overview(db, user.id)
    db.commit()
    return data


@router.post("/start")
def start(body: StartIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Liga (ou muda o valor/modo). No simulado não pede nada; com dinheiro real pede a senha e o 2FA."""
    cfg = autotrade.get_config(db, user.id)
    if not cfg.enabled and (blocked := autotrade.auto_blocked(db, user.id)):
        raise HTTPException(409, blocked)  # é um ou outro: manual ou automático
    if body.mode == "live":
        if okx_credential(db, user.id) is None:
            raise HTTPException(400, "Cadastre a chave da OKX em Configurações antes de usar dinheiro real.")
        if body.budget is None:
            raise HTTPException(400, "Diga quanto a IA pode usar no total, em USDT.")
        require_step_up(db, user, body.password, body.code, request, "modo automático com dinheiro real")
        free = autotrade.free_usdt(db, user.id)
        if free is not None and body.budget > free + autotrade.invested(db, user.id, "live") + 0.01:
            shown = f"{free:.2f}".replace(".", ",")
            raise HTTPException(400, f"Você tem {shown} USDT livres na OKX. Escolha um valor até isso (ou deposite mais).")
        audit(db, user.id, "auto_live", request, f"até {body.budget:g} USDT")
    budget = body.budget or (cfg.budget if cfg.mode == body.mode else autotrade.DEFAULT_PAPER_BUDGET)
    autotrade.enable(db, cfg, body.mode, budget)
    _launch(db, user.id, "start")
    return autotrade.overview(db, user.id)


@router.post("/stop")
def stop(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Desliga: os robôs param de comprar; quem tem posição aberta vende pela regra normal e então para."""
    autotrade.disable(db, autotrade.get_config(db, user.id))
    db.commit()
    return autotrade.overview(db, user.id)


@router.post("/run")
def run_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = autotrade.get_config(db, user.id)
    if not cfg.enabled:
        raise HTTPException(400, "Ligue o modo automático primeiro.")
    if cfg.paused_reason:
        raise HTTPException(400, "O modo automático está pausado pela proteção. Retome para testar de novo.")
    if autotrade.is_running(db, user.id):
        raise HTTPException(409, "A IA já está testando. Aguarde terminar.")
    _launch(db, user.id, "manual")
    return autotrade.overview(db, user.id)


@router.post("/resume")
def resume(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Depois da pausa da proteção: volta a operar, com o limite de perda contando do zero."""
    cfg = autotrade.get_config(db, user.id)
    if not cfg.enabled or not cfg.paused_reason:
        raise HTTPException(400, "O modo automático não está pausado.")
    autotrade.resume(db, cfg)
    _launch(db, user.id, "manual")
    return autotrade.overview(db, user.id)
