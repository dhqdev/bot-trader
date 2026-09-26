import pytest

from app.core.risk import RiskConfig, TakeProfitLevel, open_position, position_size_quote, update


def cfg(**kw) -> RiskConfig:
    base = dict(
        stop_loss_mode="percent",
        stop_loss_pct=5,
        take_profits=[],
        breakeven_at_pct=0,
        trailing_enabled=False,
    )
    base.update(kw)
    return RiskConfig(**base)


def test_stop_loss_live():
    c = cfg()
    st = open_position(100, 1, None, c)
    assert st.stop == pytest.approx(95)
    assert update(st, c, 96, 96) == []
    actions = update(st, c, 94.9, 94.9)
    assert len(actions) == 1 and actions[0].reason == "stop_loss" and actions[0].fraction == 1.0


def test_stop_gap_down_fills_at_open():
    c = cfg()
    st = open_position(100, 1, None, c)
    actions = update(st, c, high=91, low=89, open_price=90)
    assert actions[0].price == 90  # abriu abaixo do stop


def test_atr_stop():
    c = cfg(stop_loss_mode="atr", stop_loss_atr_mult=2)
    st = open_position(100, 1, 3.0, c)
    assert st.stop == pytest.approx(94)


def test_min_stop_distance_with_tiny_atr():
    """ATR minúsculo (candle de 1 min) não pode colocar o stop dentro do spread."""
    c = cfg(stop_loss_mode="atr", stop_loss_atr_mult=3)
    st = open_position(100, 1, 0.01, c)
    assert st.stop == pytest.approx(99.5)


def test_take_profits_partial_and_sequential():
    c = cfg(take_profits=[TakeProfitLevel(pct=5, size_pct=30), TakeProfitLevel(pct=10, size_pct=30)])
    st = open_position(100, 10, None, c)
    actions = update(st, c, high=111, low=100, open_price=100)  # atinge os dois alvos
    assert [a.reason for a in actions] == ["take_profit", "take_profit"]
    # 30% de 10 = 3 (fração 0.3 de 10); depois 3 de 7 restantes
    assert actions[0].fraction == pytest.approx(0.3)
    assert actions[1].fraction == pytest.approx(3 / 7)
    assert actions[0].price == pytest.approx(105) and actions[1].price == pytest.approx(110)


def test_take_profit_closes_all_when_100pct():
    c = cfg(take_profits=[TakeProfitLevel(pct=5, size_pct=100)])
    st = open_position(100, 2, None, c)
    actions = update(st, c, 106, 106)
    assert actions[0].fraction == 1.0


def test_breakeven_moves_stop_to_entry():
    c = cfg(breakeven_at_pct=2, fee_pct=0.1)
    st = open_position(100, 1, None, c)
    update(st, c, 102.5, 102.5)
    assert st.stop_kind == "breakeven"
    assert st.stop == pytest.approx(100.2)
    actions = update(st, c, 100.1, 100.1)
    assert actions and actions[0].reason == "breakeven"


def test_trailing_activation_and_follow():
    c = cfg(trailing_enabled=True, trailing_mode="percent", trailing_pct=3, trailing_activation_pct=2)
    st = open_position(100, 1, None, c)
    update(st, c, 101, 101)
    assert not st.trailing_active and st.stop_kind == "stop_loss"
    update(st, c, 110, 110)
    assert st.trailing_active and st.stop == pytest.approx(106.7)
    update(st, c, 108, 108)  # não desce o stop
    assert st.stop == pytest.approx(106.7)
    actions = update(st, c, 106.5, 106.5)
    assert actions[0].reason == "trailing_stop"


def test_position_sizing_modes():
    assert position_size_quote(RiskConfig(sizing_mode="fixed_quote", order_size_quote=25), 1000, 1000, 100, None) == 25
    assert position_size_quote(RiskConfig(sizing_mode="percent_balance", balance_percent=10), 1000, 1000, 100, None) == pytest.approx(100)
    # risco de 1% com stop a 5% => posição de 20% do patrimônio
    r = RiskConfig(sizing_mode="risk_percent", risk_percent=1, stop_loss_mode="percent", stop_loss_pct=5)
    assert position_size_quote(r, 1000, 1000, 100, None) == pytest.approx(200)
    # nunca maior que o saldo disponível
    assert position_size_quote(RiskConfig(order_size_quote=5000), 100, 100, 100, None) < 100
    assert position_size_quote(RiskConfig(order_size_quote=500, max_position_quote=50), 1000, 1000, 100, None) == 50
