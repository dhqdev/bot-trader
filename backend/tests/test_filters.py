"""Filtros da revisão com a taxa real: custo da operação e tendência do Bitcoin (backtest = robô ao vivo)."""

import pandas as pd
import pytest
from sqlalchemy import select

from app.core import market_trend
from app.core import strategies as strategies_mod
from app.core.backtest import run_backtest
from app.core.profiles import MEDIUM_RISK, RISING_SLOW_RISK, SLOW_RISK
from app.core.risk import RiskConfig
from app.db import session_scope
from app.models import BotEvent
from app.services import ranking

from .conftest import FakeMarket, make_ohlcv
from .test_engine import ScriptedStrategy, _make_bot, _positions, _step


@pytest.fixture
def scripted(monkeypatch):
    strat = ScriptedStrategy()
    strat.entry_flag, strat.exit_flag = True, False
    monkeypatch.setitem(strategies_mod.STRATEGIES, "scripted", strat)
    return strat


def _events(bot_id: int) -> list[str]:
    with session_scope() as db:
        return [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]


def test_btc_trend_uses_only_the_last_closed_day():
    coin = make_ohlcv(600, interval="1h")
    daily = make_ohlcv(120, interval="1d")
    btc = pd.DataFrame({"close_time": daily["close_time"], "close": daily["close"], "ema": daily["close"],
                        "ok": [i % 2 == 0 for i in range(len(daily))]})  # fmt: skip
    mask = market_trend.aligned(coin, 100, btc=btc)
    for i in range(0, len(coin), 37):
        closed = btc[btc["close_time"] <= coin["close_time"].iloc[i]]  # dias já fechados no fechamento do candle
        assert mask[i] == (bool(closed["ok"].iloc[-1]) if len(closed) else False)


def test_btc_trend_live_check(monkeypatch):
    daily = make_ohlcv(400, interval="1d")
    daily.loc[daily.index[-1], "close"] = daily["close"].iloc[-2] * 0.5  # último diário despencou: abaixo da média
    monkeypatch.setattr(market_trend, "_history", lambda: daily)
    market_trend.clear_cache()
    ok, reason, info = market_trend.live_check(100)
    assert ok is False and "Bitcoin abaixo da média de 100 dias" in reason and info["ok"] is False
    monkeypatch.setattr(market_trend, "_history", lambda: (_ for _ in ()).throw(RuntimeError("sem rede")))
    market_trend.clear_cache()
    assert market_trend.live_check(100) == (True, "", None)  # sem dados do Bitcoin, não bloqueia


def test_backtest_blocks_by_market_and_by_cost(scripted):
    df = make_ohlcv(800, interval="4h")
    free = run_backtest(df, "scripted", {}, RiskConfig(), "4h", start_index=100)
    assert free["metrics"]["trades"] > 0

    bear = run_backtest(df, "scripted", {}, RiskConfig(), "4h", start_index=100, market_ok=[False] * len(df))
    assert bear["metrics"]["trades"] == 0 and bear["metrics"]["entries_blocked_by_market"] > 0

    # candle anda ~1-2% e o filtro pede 5 x o custo de ida e volta (2 x (1% + 0,05%) = 2,1%): nunca compra
    costly = run_backtest(df, "scripted", {}, RiskConfig(fee_pct=1.0, min_move_mult=5), "4h", start_index=100)
    assert costly["metrics"]["trades"] == 0 and costly["metrics"]["entries_blocked_by_cost"] > 0


def test_engine_blocks_like_the_backtest(scripted, monkeypatch):
    bot_id = _make_bot({"fee_pct": 1.0, "min_move_mult": 5})
    _step(bot_id, FakeMarket())
    assert _positions(bot_id) == []
    assert any("pouco para pagar a taxa de ida e volta" in m for m in _events(bot_id))

    monkeypatch.setattr(market_trend, "live_check", lambda days: (False, f"Bitcoin abaixo da média de {days} dias (mercado em baixa)", {"days": days, "ok": False}))
    bot_id = _make_bot({"btc_trend_days": 100})
    _step(bot_id, FakeMarket())
    assert _positions(bot_id) == []
    assert any("Bitcoin abaixo da média de 100 dias" in m for m in _events(bot_id))


def test_profiles_follow_the_research():
    # lento (4h e diário): Bitcoin em alta; médio (1h e 2h): só com movimento de 1,5x o custo; rápido intocado
    assert SLOW_RISK["btc_trend_days"] == 100 and "min_move_mult" not in SLOW_RISK
    assert MEDIUM_RISK["min_move_mult"] == 1.5 and RISING_SLOW_RISK["min_move_mult"] == 1.5 and RISING_SLOW_RISK["btc_trend_days"] == 0
    for level, expected in (("baixa", {"btc_trend_days": 100, "min_move_mult": 0.0}), ("media", {"btc_trend_days": 0, "min_move_mult": 1.5}),
                            ("alta", {"btc_trend_days": 0, "min_move_mult": 0.0})):  # fmt: skip
        for robot in ranking.catalog(level):
            assert {k: robot["risk"][k] for k in expected} == expected, (level, robot["key"])
