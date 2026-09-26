"""Cálculos de resultado (PnL) para painel, bots e IA."""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.engine import binance_credential, manager
from app.core.exchange import get_market
from app.core.risk import RiskConfig
from app.core.strategies import STRATEGIES
from app.models import Bot, BotEvent, Position, utcnow

log = logging.getLogger("bot_trader.stats")


class PriceCache:
    """Evita consultar a Binance a cada requisição do painel."""

    def __init__(self, ttl: float = 10.0):
        self.ttl = ttl
        self._data: dict[bool, tuple[float, dict[str, float]]] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str, testnet: bool = False) -> float | None:
        with self._lock:
            cached = self._data.get(testnet)
            if cached is None or time.time() - cached[0] > self.ttl:
                try:
                    cached = (time.time(), get_market(testnet).prices())
                except Exception as exc:
                    log.warning("Falha ao buscar preços: %s", exc)
                    cached = (time.time() - self.ttl + 3, cached[1] if cached else {})
                self._data[testnet] = cached
        return cached[1].get(symbol)


prices = PriceCache()


def price_for(db: Session, bot: Bot) -> float | None:
    testnet = False
    if bot.mode == "live":
        cred = binance_credential(db, bot.user_id)
        testnet = bool(cred and cred.testnet)
    return prices.get(bot.symbol, testnet)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def position_view(pos: Position, price: float | None = None, fee_pct: float = 0.1) -> dict:
    view = {
        "id": pos.id,
        "bot_id": pos.bot_id,
        "symbol": pos.symbol,
        "mode": pos.mode,
        "strategy": pos.strategy,
        "status": pos.status,
        "entry_price": pos.entry_price,
        "entry_time": _iso(pos.entry_time),
        "initial_qty": pos.initial_qty,
        "qty": pos.qty,
        "cost_quote": pos.cost_quote,
        "proceeds_quote": pos.proceeds_quote,
        "fees_quote": pos.fees_quote,
        "highest_price": pos.highest_price,
        "stop_price": pos.stop_price,
        "stop_kind": pos.stop_kind,
        "trailing_active": pos.trailing_active,
        "tp_index": pos.tp_index,
        "exit_price": pos.exit_price,
        "exit_time": _iso(pos.exit_time),
        "exit_reason": pos.exit_reason,
        "pnl_quote": pos.pnl_quote,
        "pnl_pct": pos.pnl_pct,
    }
    end = pos.exit_time or utcnow()
    view["duration_seconds"] = (end - pos.entry_time).total_seconds() if pos.entry_time else None
    if pos.status == "open" and price:
        market_value = pos.qty * price * (1 - fee_pct / 100)
        unrealized = pos.proceeds_quote + market_value - pos.cost_quote
        view.update(
            current_price=price,
            market_value=market_value,
            unrealized_pnl=unrealized,
            unrealized_pct=unrealized / pos.cost_quote * 100 if pos.cost_quote else 0.0,
        )
    return view


def runtime_seconds(bot: Bot) -> float:
    total = bot.total_runtime_seconds or 0.0
    if bot.started_at:
        total += (utcnow() - bot.started_at).total_seconds()
    return total


def _today_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def bot_summary(db: Session, bot: Bot, with_price: bool = True) -> dict:
    risk = RiskConfig(**(bot.risk or {}))
    closed = list(db.scalars(select(Position).where(Position.bot_id == bot.id, Position.status == "closed")))
    open_pos = db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open"))
    price = price_for(db, bot) if with_price else None

    realized = sum(p.pnl_quote or 0.0 for p in closed)
    wins = sum(1 for p in closed if (p.pnl_quote or 0) > 0)
    today = _today_start()
    today_pnl = sum(p.pnl_quote or 0.0 for p in closed if p.exit_time and p.exit_time >= today)
    position = position_view(open_pos, price, risk.fee_pct) if open_pos else None
    unrealized = position.get("unrealized_pnl", 0.0) if position else 0.0
    strategy = STRATEGIES.get(bot.strategy)

    return {
        "id": bot.id,
        "name": bot.name,
        "symbol": bot.symbol,
        "base_asset": bot.base_asset,
        "quote_asset": bot.quote_asset,
        "interval": bot.interval,
        "strategy": bot.strategy,
        "strategy_name": strategy.name if strategy else bot.strategy,
        "strategy_params": bot.strategy_params,
        "risk": risk.model_dump(),
        "mode": bot.mode,
        "status": bot.status,
        "status_reason": bot.status_reason,
        "running": manager.is_running(bot.id),
        "paper_initial_balance": bot.paper_initial_balance,
        "paper_balance": bot.paper_balance,
        "started_at": _iso(bot.started_at),
        "runtime_seconds": runtime_seconds(bot),
        "last_tick_at": _iso(bot.last_tick_at),
        "last_signal": bot.last_signal,
        "last_error": bot.last_error,
        "created_at": _iso(bot.created_at),
        "current_price": price,
        "position": position,
        "stats": {
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
            "today_pnl": today_pnl,
            "trades": len(closed),
            "wins": wins,
            "win_rate": wins / len(closed) * 100 if closed else None,
            "best_trade": max((p.pnl_quote or 0 for p in closed), default=None),
            "worst_trade": min((p.pnl_quote or 0 for p in closed), default=None),
        },
    }


def dashboard(db: Session, user_id: int, mode: str = "all") -> dict:
    bots_q = select(Bot).where(Bot.user_id == user_id).order_by(Bot.id)
    if mode in ("paper", "live"):
        bots_q = bots_q.where(Bot.mode == mode)
    bots = list(db.scalars(bots_q))
    bot_ids = [b.id for b in bots]
    summaries = [bot_summary(db, b) for b in bots]

    positions = (
        list(db.scalars(select(Position).where(Position.bot_id.in_(bot_ids)).order_by(Position.exit_time)))
        if bot_ids
        else []
    )
    closed = [p for p in positions if p.status == "closed" and p.exit_time]
    realized = sum(p.pnl_quote or 0.0 for p in closed)
    unrealized = sum(s["stats"]["unrealized_pnl"] for s in summaries)
    wins = sum(1 for p in closed if (p.pnl_quote or 0) > 0)
    today = _today_start()

    # curva de resultado acumulado (realizado)
    curve, acc = [], 0.0
    if closed:
        curve.append({"time": closed[0].entry_time.isoformat(), "pnl": 0.0})
    for p in closed:
        acc += p.pnl_quote or 0.0
        curve.append({"time": p.exit_time.isoformat(), "pnl": round(acc, 6)})
    if closed or unrealized:
        curve.append({"time": utcnow().isoformat(), "pnl": round(acc + unrealized, 6), "live": True})

    # resultado por dia (últimos 30 dias)
    daily = defaultdict(float)
    for p in closed:
        daily[p.exit_time.strftime("%Y-%m-%d")] += p.pnl_quote or 0.0
    first_day = (today - timedelta(days=29)).date()
    daily_series = [
        {"date": (first_day + timedelta(days=i)).isoformat(), "pnl": round(daily.get((first_day + timedelta(days=i)).isoformat(), 0.0), 6)}
        for i in range(30)
    ]

    by_strategy: dict[str, dict] = {}
    for p in closed:
        s = by_strategy.setdefault(p.strategy or "?", {"strategy": p.strategy, "pnl": 0.0, "trades": 0, "wins": 0})
        s["pnl"] += p.pnl_quote or 0.0
        s["trades"] += 1
        s["wins"] += 1 if (p.pnl_quote or 0) > 0 else 0
    for s in by_strategy.values():
        strat = STRATEGIES.get(s["strategy"])
        s["name"] = strat.name if strat else s["strategy"]
        s["win_rate"] = s["wins"] / s["trades"] * 100 if s["trades"] else None

    bot_names = {b.id: b.name for b in bots}
    recent = [
        {**position_view(p), "bot_name": bot_names.get(p.bot_id, "")}
        for p in sorted(closed, key=lambda p: p.exit_time, reverse=True)[:10]
    ]
    events = (
        list(
            db.scalars(
                select(BotEvent)
                .where(BotEvent.bot_id.in_(bot_ids), BotEvent.level.in_(["trade", "error", "warn"]))
                .order_by(BotEvent.id.desc())
                .limit(15)
            )
        )
        if bot_ids
        else []
    )

    return {
        "mode": mode,
        "summary": {
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
            "today_pnl": sum(p.pnl_quote or 0.0 for p in closed if p.exit_time >= today),
            "trades": len(closed),
            "wins": wins,
            "win_rate": wins / len(closed) * 100 if closed else None,
            "open_positions": sum(1 for s in summaries if s["position"]),
            "invested": sum(s["position"]["cost_quote"] for s in summaries if s["position"]),
            "running_bots": sum(1 for s in summaries if s["running"]),
            "total_bots": len(summaries),
            "fees": sum(p.fees_quote or 0.0 for p in closed),
        },
        "equity_curve": curve,
        "daily_pnl": daily_series,
        "by_strategy": sorted(by_strategy.values(), key=lambda s: s["pnl"], reverse=True),
        "bots": summaries,
        "recent_trades": recent,
        "recent_events": [
            {
                "id": e.id,
                "bot_id": e.bot_id,
                "bot_name": bot_names.get(e.bot_id, ""),
                "level": e.level,
                "message": e.message,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
