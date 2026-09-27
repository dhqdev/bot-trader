"""Índice de medo e ganância: alinhamento sem olhar o futuro, filtro no backtest e no motor."""

import numpy as np
import pytest
from sqlalchemy import delete, select

from app.core import sentiment as sentiment_mod
from app.core.backtest import run_backtest
from app.core.engine import BotService
from app.core.exchange import PaperTrader
from app.core.risk import RiskConfig
from app.db import session_scope
from app.models import Bot, BotEvent, FearGreed, Position, User
from app.security import hash_password

from .conftest import FakeMarket, make_ohlcv
from .test_engine import scripted  # noqa: F401  (fixture)

DAY = 86_400_000


@pytest.fixture
def fng(monkeypatch):
    """Grava uma série diária controlada; limpa tudo no fim."""
    store = sentiment_mod.sentiment

    def load(values_by_day: dict[int, int]) -> None:
        store.fetcher = lambda limit=0: [{"day": d, "value": v, "label": ""} for d, v in values_by_day.items()]
        store.refresh()

    yield load
    with session_scope() as db:
        db.execute(delete(FearGreed))
    store.fetcher = sentiment_mod.fetch_fng
    store.invalidate()


def test_alignment_is_causal(fng):
    df = make_ohlcv(200, interval="1h")
    first_day = int(df["time"].iloc[0]) // DAY * DAY
    days = range(first_day - 10 * DAY, int(df["close_time"].iloc[-1]) + DAY, DAY)
    fng({d: (d // DAY) % 100 for d in days})
    now, week_ago = sentiment_mod.sentiment.aligned(df)
    for i in (0, 50, 150, 199):
        close = int(df["close_time"].iloc[i])
        day = close // DAY * DAY  # valor publicado às 00:00 do dia em que o candle fecha
        assert now[i] == (day // DAY) % 100
        assert week_ago[i] == ((day - 7 * DAY) // DAY) % 100


def test_entry_mask_modes():
    now = np.array([10.0, 30.0, 50.0, np.nan, 50.0])
    week = np.array([5.0, 40.0, 40.0, 10.0, np.nan])
    assert sentiment_mod.entry_mask("off", now, week, 20).tolist() == [True] * 5
    assert sentiment_mod.entry_mask("avoid_extreme_fear", now, week, 20).tolist() == [False, True, True, True, True]
    assert sentiment_mod.entry_mask("rising", now, week, 20).tolist() == [True, False, True, True, True]
    assert sentiment_mod.entry_mask("both", now, week, 20).tolist() == [False, False, True, True, True]


def test_backtest_respects_filter():
    df = make_ohlcv(1500, seed=3)
    n = len(df)
    fear = (np.full(n, 10.0), np.full(n, 10.0))
    base = run_backtest(df, "confluence", None, RiskConfig(sentiment_filter="off"), "1h")
    blocked = run_backtest(df, "confluence", None, RiskConfig(sentiment_filter="avoid_extreme_fear"), "1h", sentiment=fear)
    assert base["metrics"]["trades"] > 0
    assert blocked["metrics"]["trades"] == 0 and blocked["metrics"]["entries_blocked_by_sentiment"] > 0
    no_data = run_backtest(df, "confluence", None, RiskConfig(sentiment_filter="avoid_extreme_fear"), "1h")
    assert no_data["metrics"]["trades"] == base["metrics"]["trades"] and no_data["metrics"]["sentiment_filter"] == "sem dados"


def test_live_check(fng):
    import time

    today = int(time.time() * 1000) // DAY * DAY
    fng({today - 7 * DAY: 40, today: 15})
    ok, reason, info = sentiment_mod.live_check("avoid_extreme_fear", 20)
    assert not ok and "medo extremo" in reason and info["value"] == 15 and info["change_7d"] == -25
    assert sentiment_mod.live_check("off", 20)[0] is True
    ok, reason, _ = sentiment_mod.live_check("rising", 10)
    assert not ok and "caindo" in reason
    # dado velho não bloqueia nada
    with session_scope() as db:
        db.execute(delete(FearGreed))
    fng({today - 10 * DAY: 5})
    assert sentiment_mod.live_check("avoid_extreme_fear", 20)[0] is True


def test_engine_skips_buy_in_extreme_fear(fng, scripted):  # noqa: F811
    import time

    today = int(time.time() * 1000) // DAY * DAY
    fng({today - 7 * DAY: 30, today: 12})
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "fng@test.dev")) or User(email="fng@test.dev", name="F", password_hash=hash_password("x" * 8))
        db.add(user)
        db.flush()
        bot = Bot(user_id=user.id, name="F", symbol="SOLUSDT", base_asset="SOL", quote_asset="USDT", interval="1h", strategy="scripted",
                  strategy_params={}, risk={"order_size_quote": 100, "cooldown_bars": 0}, mode="paper", paper_initial_balance=1000,
                  paper_balance=1000, status="running")  # fmt: skip
        db.add(bot)
        db.flush()
        bot_id = bot.id
    market = FakeMarket()
    with session_scope() as db:
        BotService(db, db.get(Bot, bot_id), market, PaperTrader(market, 0.1, 0)).step()
    with session_scope() as db:
        assert db.scalar(select(Position).where(Position.bot_id == bot_id)) is None
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]
        assert any("medo extremo" in m for m in msgs)
        info = db.get(Bot, bot_id).last_signal["market"]
        assert info["sentiment"]["value"] == 12 and info["blocks_entry"] is True
