import pytest

from app.core.backtest import run_backtest
from app.core.risk import RiskConfig
from app.core.strategies import STRATEGIES

from .conftest import make_ohlcv


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_backtest_runs(key, ohlcv):
    res = run_backtest(ohlcv, key, None, RiskConfig(sizing_mode="percent_balance", balance_percent=100), "1h", 1000)
    m = res["metrics"]
    for field in ("total_return_pct", "max_drawdown_pct", "sharpe", "trades", "win_rate_pct", "buy_hold_return_pct"):
        assert field in m
    assert m["max_drawdown_pct"] <= 0
    assert res["equity_curve"] and res["equity_curve"][-1]["equity"] == pytest.approx(m["final_equity"], rel=1e-3)


def test_pnl_is_consistent_with_equity(ohlcv):
    res = run_backtest(ohlcv, "supertrend", None, RiskConfig(sizing_mode="percent_balance", balance_percent=100), "1h", 1000)
    total_pnl = sum(t["pnl"] for t in res["trades"])
    assert res["metrics"]["final_equity"] == pytest.approx(1000 + total_pnl, abs=0.05)


def test_fees_cost_money():
    """Com taxa e slippage altas, a mesma estratégia deve render menos."""
    df = make_ohlcv(2000, seed=3)
    cheap = run_backtest(df, "ema_cross", None, RiskConfig(fee_pct=0.0, sizing_mode="percent_balance", balance_percent=100), "1h", 1000, slippage_pct=0)
    pricey = run_backtest(df, "ema_cross", None, RiskConfig(fee_pct=1.0, sizing_mode="percent_balance", balance_percent=100), "1h", 1000, slippage_pct=0.5)
    assert cheap["metrics"]["trades"] > 0
    assert pricey["metrics"]["final_equity"] < cheap["metrics"]["final_equity"]


def test_stop_loss_limits_loss():
    df = make_ohlcv(2000, seed=5, vol=0.02)
    risk = RiskConfig(stop_loss_mode="percent", stop_loss_pct=2, take_profits=[], trailing_enabled=False,
                      breakeven_at_pct=0, sizing_mode="percent_balance", balance_percent=100, fee_pct=0.1)  # fmt: skip
    res = run_backtest(df, "confluence", None, risk, "1h", 1000, slippage_pct=0)
    stops = [t for t in res["trades"] if t["exit_reason"] == "stop_loss"]
    # perda por stop ~2% + taxas; gaps podem piorar um pouco
    assert all(t["pnl_pct"] > -6 for t in stops)
