from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exchange import BinanceTrader
from app.db import get_db
from app.deps import get_current_user
from app.models import Bot, Credential, User
from app.schemas import AnthropicKeyIn, BinanceKeysIn
from app.security import decrypt, encrypt, mask

router = APIRouter(prefix="/settings", tags=["settings"])


def _get(db: Session, user_id: int, provider: str) -> Credential | None:
    return db.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == provider))


def _masked(cred: Credential | None) -> str | None:
    if cred is None:
        return None
    try:
        return mask(decrypt(cred.key_enc))
    except ValueError:
        return "(ilegível: refaça o cadastro)"


@router.get("/credentials")
def credentials(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    binance = _get(db, user.id, "binance")
    anthropic = _get(db, user.id, "anthropic")
    env_key = bool(get_settings().anthropic_api_key)
    return {
        "binance": {
            "configured": binance is not None,
            "api_key": _masked(binance),
            "testnet": binance.testnet if binance else False,
            "updated_at": binance.updated_at.isoformat() if binance else None,
        },
        "anthropic": {
            "configured": anthropic is not None or env_key,
            "api_key": _masked(anthropic) if anthropic else ("(variável de ambiente)" if env_key else None),
            "source": "db" if anthropic else ("env" if env_key else None),
            "model": get_settings().ai_model,
        },
    }


@router.put("/binance")
def save_binance(body: BinanceKeysIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "binance") or Credential(user_id=user.id, provider="binance")
    cred.key_enc = encrypt(body.api_key.strip())
    cred.secret_enc = encrypt(body.api_secret.strip())
    cred.testnet = body.testnet
    db.add(cred)
    db.commit()
    return {"ok": True}


@router.delete("/binance")
def delete_binance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    live_running = db.scalar(select(Bot).where(Bot.user_id == user.id, Bot.mode == "live", Bot.status == "running"))
    if live_running:
        raise HTTPException(400, "Pare os bots em modo real antes de remover as chaves.")
    cred = _get(db, user.id, "binance")
    if cred:
        db.delete(cred)
        db.commit()
    return {"ok": True}


@router.post("/binance/test")
def test_binance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "binance")
    if cred is None:
        raise HTTPException(400, "Cadastre as chaves primeiro.")
    try:
        trader = BinanceTrader(decrypt(cred.key_enc), decrypt(cred.secret_enc or ""), testnet=cred.testnet)
        summary = trader.account_summary()
    except Exception as exc:
        raise HTTPException(400, f"Falha ao conectar: {exc}") from exc
    summary["balances"] = sorted(summary["balances"], key=lambda b: b["free"] + b["locked"], reverse=True)[:20]
    return {"ok": True, "testnet": cred.testnet, **summary}


@router.put("/anthropic")
def save_anthropic(body: AnthropicKeyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "anthropic") or Credential(user_id=user.id, provider="anthropic")
    cred.key_enc = encrypt(body.api_key.strip())
    db.add(cred)
    db.commit()
    return {"ok": True}


@router.delete("/anthropic")
def delete_anthropic(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "anthropic")
    if cred:
        db.delete(cred)
        db.commit()
    return {"ok": True}
