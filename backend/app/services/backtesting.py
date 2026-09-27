import threading
import time

import pandas as pd

from app.core.backtest import run_backtest
from app.core.exchange import INTERVAL_MINUTES, get_market
from app.core.risk import RiskConfig
from app.core.sentiment import sentiment
from app.core.strategies import STRATEGIES, get_strategy

MAX_BARS = 20_000
_CACHE_TTL = 300
_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def history(symbol: str, interval: str, bars: int) -> pd.DataFrame:
    """Candles fechados com cache curto (ajustar parâmetros fica instantâneo)."""
    bars = min(bars, MAX_BARS)
    key = (symbol, interval)
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL and len(hit[1]) >= bars:
        return hit[1].tail(bars).reset_index(drop=True)
    df = get_market(False).klines(symbol, interval, limit=bars)
    if df.empty:
        raise ValueError(f"Sem dados para {symbol} {interval}.")
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
