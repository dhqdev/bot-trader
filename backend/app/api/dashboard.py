from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.engine import binance_credential
from app.core.exchange import BinanceTrader, get_market
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.security import decrypt
from app.services import stats

router = APIRouter(tags=["dashboard"])

STABLES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI"}


@router.get("/dashboard")
def dashboard(
    mode: str = Query("all", pattern="^(all|paper|live)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return stats.dashboard(db, user.id, mode)


@router.get("/account/balance")
def account_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Carteira Spot real, avaliada em USDT."""
    cred = binance_credential(db, user.id)
    if cred is None:
        raise HTTPException(400, "Chaves da Binance não configuradas.")
    try:
        trader = BinanceTrader(decrypt(cred.key_enc), decrypt(cred.secret_enc or ""), testnet=cred.testnet)
        summary = trader.account_summary()
        prices = get_market(cred.testnet).prices()
    except Exception as exc:
        raise HTTPException(502, f"Falha ao consultar a Binance: {exc}") from exc

    assets, total = [], 0.0
    for b in summary["balances"]:
        amount = b["free"] + b["locked"]
        if b["asset"] in STABLES:
            value = amount
        else:
            price = prices.get(f"{b['asset']}USDT")
            value = amount * price if price else None
        if value is not None:
            total += value
        assets.append({**b, "total": amount, "value_usdt": value})
    assets.sort(key=lambda a: a["value_usdt"] or 0, reverse=True)
    return {"total_usdt": total, "assets": assets, "testnet": cred.testnet, "can_trade": summary["can_trade"]}
