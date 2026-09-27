from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.engine import make_live_trader, market_params, okx_credential
from app.core.markets import get_market
from app.db import get_db
from app.deps import get_current_user
from app.models import Bot, User
from app.services import stats

router = APIRouter(tags=["dashboard"])

STABLES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI", "USD"}


@router.get("/dashboard")
def dashboard(
    mode: str = Query("all", pattern="^(all|paper|live)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return stats.dashboard(db, user.id, mode)


def _wallet(db: Session, user: User) -> dict:
    cred = okx_credential(db, user.id)
    view = {"exchange": "okx", "label": "OKX", "testnet": bool(cred.testnet), "total_usdt": None, "assets": [], "error": None}
    try:
        # o trader real só lê a carteira aqui; nenhuma ordem é enviada
        trader = make_live_trader(db, Bot(user_id=user.id, mode="live"))
        summary = trader.account_summary()
        demo, region = market_params(db, user.id, "live")
        prices = get_market(demo, region).prices()
    except Exception as exc:
        view["error"] = f"Falha ao consultar a OKX: {exc}"[:300]
        return view
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
    view.update(total_usdt=total, assets=assets, can_trade=summary["can_trade"])
    return view


@router.get("/account/balance")
def account_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Carteira Spot real na OKX, avaliada em USDT."""
    wallets = [_wallet(db, user)] if okx_credential(db, user.id) is not None else []
    return {"wallets": wallets}
