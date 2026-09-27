from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.exchange import INTERVAL_MINUTES
from app.core.markets import get_market
from app.deps import get_current_user

router = APIRouter(prefix="/market", tags=["market"], dependencies=[Depends(get_current_user)])


@router.get("/intervals")
def intervals():
    return list(INTERVAL_MINUTES)


@router.get("/symbols")
def symbols(quote: str = Query("USDT", max_length=10)):
    try:
        return get_market().symbols(quote)
    except Exception as exc:
        raise HTTPException(502, f"OKX indisponível: {exc}") from exc


@router.get("/ticker")
def ticker(symbol: str = Query(..., max_length=32)):
    try:
        return get_market().ticker_24h(symbol.upper())
    except Exception as exc:
        raise HTTPException(400, f"Não foi possível obter {symbol}: {exc}") from exc


@router.get("/klines")
def klines(symbol: str = Query(..., max_length=32), interval: str = "1h", limit: int = Query(300, ge=10, le=1500)):
    if interval not in INTERVAL_MINUTES:
        raise HTTPException(400, "Intervalo inválido")
    try:
        df = get_market().klines(symbol.upper(), interval, limit=limit, closed_only=False)
    except Exception as exc:
        raise HTTPException(400, f"Não foi possível obter candles: {exc}") from exc
    return [
        {"time": int(r.time) // 1000, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume}
        for r in df.itertuples()
    ]
