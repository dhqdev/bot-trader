"""Retrato técnico de um par, usado pela IA para contextualizar análises."""

import math

from app.core import indicators as ta
from app.core.exchange import get_market


def _r(v, nd=4):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


def snapshot(symbol: str, interval: str = "1h") -> dict:
    market = get_market()
    df = market.klines(symbol, interval, limit=600)
    if len(df) < 210:
        raise ValueError("Histórico insuficiente para análise.")
    close, high, low = df["close"], df["high"], df["low"]
    price = float(close.iloc[-1])
    ema20, ema50, ema200 = (ta.ema(close, n).iloc[-1] for n in (20, 50, 200))
    adx, pdi, mdi = (s.iloc[-1] for s in ta.adx(high, low, close, 14))
    rsi = ta.rsi(close, 14).iloc[-1]
    atr_pct = ta.atr(high, low, close, 14).iloc[-1] / price * 100
    _, st_dir = ta.supertrend(high, low, close, 10, 3.0)
    mid, upper, lower = (s.iloc[-1] for s in ta.bollinger(close, 20, 2.0))
    _, _, hist = ta.macd(close)

    if price > ema200 and ema50 > ema200 and adx >= 25 and pdi > mdi:
        regime = "tendência de alta forte"
    elif price > ema200 and ema50 > ema200:
        regime = "tendência de alta"
    elif price < ema200 and ema50 < ema200 and adx >= 25 and mdi > pdi:
        regime = "tendência de baixa forte"
    elif price < ema200 and ema50 < ema200:
        regime = "tendência de baixa"
    else:
        regime = "lateral / transição"

    try:
        t24 = market.ticker_24h(symbol)
    except Exception:
        t24 = {}

    def ret(n: int) -> float | None:
        return _r((price / float(close.iloc[-1 - n]) - 1) * 100, 2) if len(close) > n else None

    return {
        "symbol": symbol,
        "interval": interval,
        "price": price,
        "change_24h_pct": t24.get("change_pct"),
        "quote_volume_24h": t24.get("quote_volume"),
        "return_last_20_bars_pct": ret(20),
        "return_last_100_bars_pct": ret(100),
        "regime": regime,
        "rsi_14": _r(rsi, 1),
        "adx_14": _r(adx, 1),
        "plus_di": _r(pdi, 1),
        "minus_di": _r(mdi, 1),
        "atr_pct": _r(atr_pct, 2),
        "price_vs_ema20_pct": _r((price / ema20 - 1) * 100, 2),
        "price_vs_ema50_pct": _r((price / ema50 - 1) * 100, 2),
        "price_vs_ema200_pct": _r((price / ema200 - 1) * 100, 2),
        "supertrend": "alta" if st_dir.iloc[-1] > 0 else "baixa",
        "bollinger_percent_b": _r((price - lower) / (upper - lower), 2) if upper != lower else None,
        "macd_histogram": _r(hist.iloc[-1], 8),
        "high_100_bars": float(high.tail(100).max()),
        "low_100_bars": float(low.tail(100).min()),
    }
