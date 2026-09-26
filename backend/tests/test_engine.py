"""Motor em modo simulado com mercado falso: compra, stop, alvos e saída por sinal."""

import pandas as pd
import pytest
from sqlalchemy import select

from app.core import strategies as strategies_mod
from app.core.engine import BotRunner, BotService, manager
from app.core.exchange import PaperTrader
from app.core.strategies.base import Strategy, StrategyOutput, always
from app.db import session_scope
from app.models import Bot, BotEvent, Order, Position, User
from app.security import hash_password

from .conftest import FakeMarket


class ScriptedStrategy(Strategy):
    """Entrada/saída controladas pelo teste."""

    key = "scripted"
    name = "Scripted"
    style = "teste"
    description = ""
    params = []
    entry_flag = True
    exit_flag = False

    def warmup(self, p):
        return 60

    def compute(self, df: pd.DataFrame, p: dict) -> StrategyOutput:
        entry = always(df.index, self.entry_flag)
        exit_ = always(df.index, self.exit_flag)
        return StrategyOutput(entry=entry, exit=exit_, entry_conditions={"ok": entry}, exit_conditions={"sair": exit_})


@pytest.fixture
def scripted(monkeypatch):
    strat = ScriptedStrategy()
    monkeypatch.setitem(strategies_mod.STRATEGIES, "scripted", strat)
    return strat


def _make_bot(risk: dict | None = None) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "engine@test.dev"))
        if user is None:
            user = User(email="engine@test.dev", name="Engine", password_hash=hash_password("x" * 8))
            db.add(user)
            db.flush()
        bot = Bot(
            user_id=user.id,
            name="Teste",
            symbol="SOLUSDT",
            base_asset="SOL",
            quote_asset="USDT",
            interval="1h",
            strategy="scripted",
            strategy_params={},
            risk={
                "sizing_mode": "fixed_quote",
                "order_size_quote": 100,
                "stop_loss_mode": "percent",
                "stop_loss_pct": 5,
                "take_profits": [{"pct": 5, "size_pct": 50}],
                "breakeven_at_pct": 0,
                "trailing_enabled": False,
                "cooldown_bars": 0,
                **(risk or {}),
            },
            mode="paper",
            paper_initial_balance=1000,
            paper_balance=1000,
            status="running",
        )
        db.add(bot)
        db.flush()
        return bot.id


def _step(bot_id: int, market: FakeMarket, evaluate: bool = False) -> None:
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        if evaluate:
            bot.last_candle_time = None  # força avaliar o candle
        svc = BotService(db, bot, market, PaperTrader(market, fee_pct=0.1, slippage_pct=0))
        svc.step()


def _positions(bot_id: int) -> list[Position]:
    with session_scope() as db:
        return list(db.scalars(select(Position).where(Position.bot_id == bot_id).order_by(Position.id)))


def test_buy_then_stop_loss(scripted):
    market = FakeMarket()
    bot_id = _make_bot()
    entry_price = market.current

    _step(bot_id, market)  # candle novo -> sinal de entrada -> compra
    [pos] = _positions(bot_id)
    assert pos.status == "open"
    assert pos.cost_quote == pytest.approx(100, rel=1e-3)
    assert pos.stop_price == pytest.approx(entry_price * 0.95, rel=1e-6)

    market.current = entry_price * 0.94  # abaixo do stop
    _step(bot_id, market)
    [pos] = _positions(bot_id)
    assert pos.status == "closed" and pos.exit_reason == "stop_loss"
    assert pos.pnl_quote < 0
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        assert bot.paper_balance == pytest.approx(1000 + pos.pnl_quote, abs=1e-6)
        assert len(list(db.scalars(select(Order).where(Order.bot_id == bot_id)))) == 2


def test_take_profit_then_signal_exit(scripted):
    market = FakeMarket()
    bot_id = _make_bot()
    entry_price = market.current
    _step(bot_id, market)

    market.current = entry_price * 1.06  # alvo de 5% -> vende 50%
    _step(bot_id, market)
    [pos] = _positions(bot_id)
    assert pos.status == "open" and pos.tp_index == 1
    assert pos.qty == pytest.approx(pos.initial_qty * 0.5, rel=1e-2)

    scripted.exit_flag = True  # estratégia manda sair no próximo candle
    scripted.entry_flag = False
    _step(bot_id, market, evaluate=True)
    [pos] = _positions(bot_id)
    assert pos.status == "closed" and pos.exit_reason == "signal"
    assert pos.pnl_quote > 0


def test_min_notional_blocks_tiny_orders(scripted):
    market = FakeMarket()
    bot_id = _make_bot({"order_size_quote": 2})
    _step(bot_id, market)
    assert _positions(bot_id) == []
    with session_scope() as db:
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]
    assert any("abaixo do mínimo" in m for m in msgs)


def test_daily_loss_limit_blocks_entries(scripted):
    market = FakeMarket()
    bot_id = _make_bot({"max_daily_loss_quote": 1})
    entry_price = market.current
    _step(bot_id, market)
    market.current = entry_price * 0.9
    _step(bot_id, market)  # stop -> perda > 1 USDT
    market.current = entry_price
    _step(bot_id, market, evaluate=True)
    assert len(_positions(bot_id)) == 1  # não abriu outra
    with session_scope() as db:
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]
    assert any("perda diária" in m for m in msgs)


def test_runner_tick_uses_injected_market(scripted, monkeypatch):
    market = FakeMarket()
    bot_id = _make_bot()
    monkeypatch.setattr(manager, "market_factory", lambda db, bot: market)
    runner = BotRunner(bot_id, manager)
    assert runner.tick() is True
    assert len(_positions(bot_id)) == 1
    with session_scope() as db:
        db.get(Bot, bot_id).status = "stopped"
    assert runner.tick() is False


class LimitedWalletTrader(PaperTrader):
    """Execução "real" falsa: a carteira tem só parte do ativo (usuário vendeu à mão)."""

    mode = "live"

    def __init__(self, market, base_available: float | None = None):
        super().__init__(market, fee_pct=0.1, slippage_pct=0)
        self.base_available = base_available

    def free(self, asset):
        if asset == "USDT":
            return 10_000.0
        return self.base_available if self.base_available is not None else 1e9


def test_live_sell_does_not_count_coins_missing_from_wallet(scripted):
    market = FakeMarket()
    bot_id = _make_bot()
    with session_scope() as db:
        db.get(Bot, bot_id).mode = "live"
    trader = LimitedWalletTrader(market)
    with session_scope() as db:
        BotService(db, db.get(Bot, bot_id), market, trader).step()
    [pos] = _positions(bot_id)
    trader.base_available = pos.qty / 2  # só metade continua na carteira

    scripted.exit_flag, scripted.entry_flag = True, False
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        bot.last_candle_time = None
        BotService(db, bot, market, trader).step()
    [pos] = _positions(bot_id)
    assert pos.status == "closed"
    # recebeu só pela metade vendida: o resultado não é inflado pela metade que não existia
    assert pos.proceeds_quote == pytest.approx(pos.cost_quote / 2, rel=0.02)
    assert pos.pnl_pct == pytest.approx(-50, abs=1.5)


def test_bots_with_removed_strategy_are_migrated():
    bot_id = _make_bot()
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        bot.strategy, bot.strategy_params, bot.status = "supertrend", {"multiplier": 4}, "stopped"
    manager.start()
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        assert bot.strategy == "confluence"
        assert bot.strategy_params["ema_fast"] == 9  # padrões da substituta
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]
    assert any("removida" in m for m in msgs)
