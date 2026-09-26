"""Backtest realista, usando exatamente a mesma estratégia e o mesmo
gerenciador de risco do motor ao vivo.

- O sinal é calculado no fechamento do candle e executado na abertura do
  próximo (como acontece ao vivo), com taxa e slippage.
- Stop, break-even, trailing e alvos parciais são checados dentro de cada
  candle (máxima/mínima). Se stop e alvo forem tocados no mesmo candle,
  assume o pior caso.
"""

import math
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.core import indicators as ta
from app.core.exchange import INTERVAL_MINUTES
from app.core.risk import RiskConfig, open_position, position_size_quote, update
from app.core.strategies import get_strategy

MIN_ORDER_QUOTE = 5.0  # a Binance recusa ordens abaixo de ~5 USDT


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def run_backtest(
    df: pd.DataFrame,
    strategy_key: str,
    params: dict | None,
    risk: RiskConfig,
    interval: str,
    initial_capital: float = 1000.0,
    slippage_pct: float = 0.05,
    max_curve_points: int = 600,
) -> dict:
    strategy = get_strategy(strategy_key)
    resolved = strategy.resolve_params(params)
    if len(df) < 50:
        raise ValueError("Poucos candles para o backtest.")

    out = strategy.run(df, resolved)
    atr = ta.atr(df["high"], df["low"], df["close"], 14).to_numpy()
    opens, highs, lows, closes = (df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    times = df["time"].to_numpy()
    entry, exit_ = out.entry.to_numpy(), out.exit.to_numpy()

    n = len(df)
    start = min(max(strategy.warmup(resolved) // 2, 30), n - 2)
    fee = risk.fee_pct / 100
    slip = slippage_pct / 100

    cash = initial_capital
    state = None
    trade: dict | None = None
    pending: str | None = None
    cooldown_until = -1
    daily_pnl: dict[str, float] = {}
    trades: list[dict] = []
    equity = np.full(n, np.nan)
    bars_in_market = 0

    def sell(qty: float, price: float, reason: str, i: int) -> None:
        nonlocal cash
        gross = qty * price
        fee_q = gross * fee
        cash += gross - fee_q
        state.qty -= qty
        trade["proceeds"] += gross - fee_q
        trade["fees"] += fee_q
        trade["exits"].append({"time": int(times[i]), "price": price, "qty": qty, "reason": reason})

    def close_trade(i: int, reason: str) -> None:
        nonlocal state, trade, cooldown_until
        pnl = trade["proceeds"] - trade["cost"]
        sold = sum(e["qty"] for e in trade["exits"])
        trades.append(
            {
                "entry_time": trade["entry_time"],
                "entry_price": trade["entry_price"],
                "exit_time": int(times[i]),
                "exit_price": sum(e["price"] * e["qty"] for e in trade["exits"]) / sold if sold else 0.0,
                "exit_reason": reason,
                "partial_exits": len(trade["exits"]) - 1,
                "cost": trade["cost"],
                "pnl": pnl,
                "pnl_pct": pnl / trade["cost"] * 100 if trade["cost"] else 0.0,
                "fees": trade["fees"],
                "bars": i - trade["entry_index"],
            }
        )
        day = _day(int(times[i]))
        daily_pnl[day] = daily_pnl.get(day, 0.0) + pnl
        state, trade = None, None
        cooldown_until = i + risk.cooldown_bars

    for i in range(start, n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        # 1) executa a ordem gerada no fechamento anterior, na abertura deste candle
        if pending == "buy" and state is None:
            price = o * (1 + slip)
            size = position_size_quote(risk, cash, cash, price, atr[i - 1] if not math.isnan(atr[i - 1]) else None)
            if size >= MIN_ORDER_QUOTE:
                qty = size / (price * (1 + fee))
                cost = qty * price * (1 + fee)
                cash -= cost
                state = open_position(price, qty, atr[i - 1] if not math.isnan(atr[i - 1]) else None, risk)
                trade = {
                    "entry_time": int(times[i]),
                    "entry_price": price,
                    "entry_index": i,
                    "cost": cost,
                    "proceeds": 0.0,
                    "fees": cost - qty * price,
                    "exits": [],
                }
        elif pending == "sell" and state is not None:
            sell(state.qty, o * (1 - slip), "signal", i)
            close_trade(i, "signal")
        pending = None

        # 2) gerenciamento de risco dentro do candle
        if state is not None:
            bars_in_market += 1
            for action in update(state, risk, h, l, o):
                price = action.price * (1 - slip)
                qty = state.qty * action.fraction
                sell(qty, price, action.reason, i)
                if action.fraction >= 1.0 or state.qty <= state.initial_qty * 1e-6:
                    close_trade(i, action.reason)
                    break

        # 3) sinais no fechamento
        blocked_today = risk.max_daily_loss_quote > 0 and daily_pnl.get(_day(int(times[i])), 0.0) <= -risk.max_daily_loss_quote
        if state is None and entry[i] and i >= cooldown_until and not blocked_today and i < n - 1:
            pending = "buy"
        elif state is not None and exit_[i]:
            pending = "sell"

        equity[i] = cash + (state.qty * c * (1 - fee) if state is not None else 0.0)

    if state is not None:  # fecha no último preço para medir o resultado
        sell(state.qty, closes[-1] * (1 - slip), "end", n - 1)
        close_trade(n - 1, "end")
        equity[-1] = cash

    return _report(df, equity[start:], times[start:], closes[start:], trades, initial_capital, interval, bars_in_market, max_curve_points)


def _report(df, equity, times, closes, trades, initial_capital, interval, bars_in_market, max_points) -> dict:
    equity = pd.Series(equity).ffill().fillna(initial_capital).to_numpy()
    final = float(equity[-1])
    peak = np.maximum.accumulate(equity)
    drawdown = (equity / peak - 1) * 100
    returns = np.diff(equity) / equity[:-1]
    bars_per_year = 365 * 24 * 60 / INTERVAL_MINUTES.get(interval, 60)
    sharpe = float(returns.mean() / returns.std() * math.sqrt(bars_per_year)) if returns.std() > 0 else 0.0

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    buy_hold = (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0.0

    step = max(1, len(equity) // max_points)
    curve = [
        {"time": int(times[i]), "equity": round(float(equity[i]), 4), "buy_hold": round(initial_capital * closes[i] / closes[0], 4)}
        for i in range(0, len(equity), step)
    ]
    if curve and curve[-1]["time"] != int(times[-1]):
        curve.append({"time": int(times[-1]), "equity": round(final, 4), "buy_hold": round(initial_capital * closes[-1] / closes[0], 4)})

    metrics = {
        "initial_capital": initial_capital,
        "final_equity": round(final, 2),
        "total_return_pct": round((final / initial_capital - 1) * 100, 2),
        "buy_hold_return_pct": round(buy_hold, 2),
        "max_drawdown_pct": round(float(drawdown.min()), 2),
        "sharpe": round(sharpe, 2),
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (None if not wins else 999.0),
        "avg_trade_pct": round(float(np.mean([t["pnl_pct"] for t in trades])), 2) if trades else 0.0,
        "avg_win_pct": round(float(np.mean([t["pnl_pct"] for t in wins])), 2) if wins else 0.0,
        "avg_loss_pct": round(float(np.mean([t["pnl_pct"] for t in losses])), 2) if losses else 0.0,
        "best_trade_pct": round(max(t["pnl_pct"] for t in trades), 2) if trades else 0.0,
        "worst_trade_pct": round(min(t["pnl_pct"] for t in trades), 2) if trades else 0.0,
        "fees_paid": round(sum(t["fees"] for t in trades), 2),
        "exposure_pct": round(bars_in_market / len(equity) * 100, 1) if len(equity) else 0.0,
        "avg_bars_in_trade": round(float(np.mean([t["bars"] for t in trades])), 1) if trades else 0.0,
        "exit_reasons": dict(Counter(t["exit_reason"] for t in trades)),
        "bars": len(equity),
        "period_start": int(times[0]),
        "period_end": int(times[-1]),
    }
    return {"metrics": metrics, "equity_curve": curve, "trades": trades}
