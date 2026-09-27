import threading
import time

import pandas as pd
from sqlalchemy import delete, func, select

from app.core.backtest import run_backtest
from app.core.exchange import INTERVAL_MINUTES, interval_ms, now_ms
from app.core.markets import get_market
from app.core.risk import RiskConfig
from app.core.sentiment import sentiment
from app.core.strategies import STRATEGIES, get_strategy
from app.db import session_scope
from app.models import CandleCache

MAX_BARS = 20_000
KEEP_BARS = 25_000  # por par e tempo de candle, no banco
_CACHE_TTL = 900  # em memória: ajustar parâmetros no laboratório fica instantâneo
_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()
_fetch_lock = threading.Lock()
PRICE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def _load_cached(symbol: str, interval: str) -> pd.DataFrame:
    with session_scope() as db:
        rows = db.execute(
            select(CandleCache.time, CandleCache.open, CandleCache.high, CandleCache.low, CandleCache.close, CandleCache.volume)
            .where(CandleCache.symbol == symbol, CandleCache.interval == interval)
            .order_by(CandleCache.time)
        ).all()
    df = pd.DataFrame([tuple(r) for r in rows], columns=PRICE_COLUMNS)
    if not df.empty:
        df["time"] = df["time"].astype("int64")
        df["close_time"] = df["time"] + interval_ms(interval) - 1
    return df


def _store(symbol: str, interval: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    times = [int(t) for t in df["time"]]
    with session_scope() as db:
        existing = set(
            db.scalars(
                select(CandleCache.time).where(
                    CandleCache.symbol == symbol, CandleCache.interval == interval, CandleCache.time.between(min(times), max(times))
                )
            )
        )
        db.add_all(
            CandleCache(symbol=symbol, interval=interval, time=int(r.time), open=float(r.open), high=float(r.high),
                        low=float(r.low), close=float(r.close), volume=float(r.volume))  # fmt: skip
            for r in df.itertuples()
            if int(r.time) not in existing
        )
        db.flush()
        count = db.scalar(select(func.count()).select_from(CandleCache).where(CandleCache.symbol == symbol, CandleCache.interval == interval))
        if count and count > KEEP_BARS:
            cutoff = db.scalar(
                select(CandleCache.time)
                .where(CandleCache.symbol == symbol, CandleCache.interval == interval)
                .order_by(CandleCache.time.desc())
                .offset(KEEP_BARS)
                .limit(1)
            )
            db.execute(delete(CandleCache).where(CandleCache.symbol == symbol, CandleCache.interval == interval, CandleCache.time <= cutoff))


def history(symbol: str, interval: str, bars: int) -> pd.DataFrame:
    """Candles fechados da OKX. Guarda o que baixa no banco e, nas próximas vezes,
    busca só o que falta (candles novos e, se precisar, mais antigos)."""
    bars = min(bars, MAX_BARS)
    key = (symbol, interval)
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL and len(hit[1]) >= bars:
        return hit[1].tail(bars).reset_index(drop=True)

    with _fetch_lock:  # dois backtests ao mesmo tempo não baixam o mesmo histórico duas vezes
        market = get_market()
        cached = _load_cached(symbol, interval)
        fresh: list[pd.DataFrame] = []
        if cached.empty:
            fresh.append(market.klines(symbol, interval, limit=bars))
        else:
            step = interval_ms(interval)
            last_closed = (now_ms() // step) * step - step
            newest, oldest = int(cached["time"].iloc[-1]), int(cached["time"].iloc[0])
            missing_new = (last_closed - newest) // step
            if missing_new > 0:
                recent = market.klines(symbol, interval, limit=int(missing_new) + 2)
                fresh.append(recent[recent["time"] > newest])
            have = len(cached) + sum(len(f) for f in fresh)
            if have < bars:
                fresh.append(market.klines(symbol, interval, limit=bars - have, before=oldest))
        for part in fresh:
            _store(symbol, interval, part)

    frames = [f for f in [cached, *fresh] if f is not None and not f.empty]
    if not frames:
        raise ValueError(f"Sem dados para {symbol} {interval}.")
    df = pd.concat(frames, ignore_index=True).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df = df.tail(bars).reset_index(drop=True)
    with _lock:
        _cache[key] = (time.time(), df)
    return df


def aligned_sentiment(df: pd.DataFrame, risk: RiskConfig):
    """Índice de medo e ganância alinhado aos candles (o mesmo filtro que o bot usa ao vivo)."""
    if risk.sentiment_filter == "off":
        return None
    try:
        return sentiment.aligned(df)
    except Exception:
        return None


def bars_for(interval: str, days: int, warmup: int) -> int:
    return int(days * 1440 / INTERVAL_MINUTES[interval]) + warmup


def backtest(
    symbol: str,
    interval: str,
    strategy: str,
    params: dict | None,
    risk: RiskConfig,
    days: int,
    initial_capital: float = 1000.0,
    include_candles: bool = False,
) -> dict:
    strat = get_strategy(strategy)
    resolved = strat.resolve_params(params)
    warmup = strat.warmup(resolved) // 2
    df = history(symbol, interval, bars_for(interval, days, warmup))
    result = run_backtest(df, strategy, resolved, risk, interval, initial_capital, sentiment=aligned_sentiment(df, risk))
    result["request"] = {
        "symbol": symbol,
        "interval": interval,
        "strategy": strategy,
        "strategy_name": strat.name,
        "params": resolved,
        "risk": risk.model_dump(),
        "days": days,
        "initial_capital": initial_capital,
    }
    if include_candles:
        # no máximo 5000 candles para o gráfico (os mais recentes)
        start = max(result["metrics"]["period_start"], int(df["time"].iloc[max(len(df) - 5000, 0)]))
        mask = df["time"] >= start
        out = strat.run(df, resolved)
        result["candles"] = [
            {"time": int(r.time) // 1000, "open": r.open, "high": r.high, "low": r.low, "close": r.close}
            for r in df[mask].itertuples()
        ]
        result["overlays"] = {
            name: [
                {"time": int(t) // 1000, "value": round(float(v), 8)}
                for t, v in zip(df["time"][mask], series[mask])
                if pd.notna(v)
            ]
            for name, series in out.overlays.items()
        }
    return result


def compare(symbol: str, interval: str, days: int, risk: RiskConfig | None = None, initial_capital: float = 1000.0) -> list[dict]:
    """Roda todas as estratégias com parâmetros padrão no mesmo período."""
    risk = risk or RiskConfig()
    rows = []
    for key, strat in STRATEGIES.items():
        try:
            m = backtest(symbol, interval, key, None, risk, days, initial_capital)["metrics"]
            rows.append({"strategy": key, "name": strat.name, **{k: m[k] for k in (
                "total_return_pct", "buy_hold_return_pct", "max_drawdown_pct", "sharpe", "trades",
                "win_rate_pct", "profit_factor", "exposure_pct",
            )}})  # fmt: skip
        except Exception as exc:
            rows.append({"strategy": key, "name": strat.name, "error": str(exc)})
    return sorted(rows, key=lambda r: r.get("total_return_pct", -1e9), reverse=True)
