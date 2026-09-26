import pytest

from app.core.strategies import STRATEGIES

from .conftest import make_ohlcv


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_output_shape(key, ohlcv):
    out = STRATEGIES[key].run(ohlcv)
    assert len(out.entry) == len(ohlcv) and len(out.exit) == len(ohlcv)
    assert out.entry.dtype == bool and out.exit.dtype == bool
    assert out.entry_conditions and out.exit_conditions
    snap = out.snapshot()
    assert isinstance(snap["entry"], bool)
    assert all("label" in c and "ok" in c for c in snap["entry_checks"])


RELAXED = {"bb_reversion": {"rsi_entry": 40, "use_trend_filter": False}}  # seletiva demais p/ dados sintéticos


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_generates_signals(key):
    df = make_ohlcv(3000, seed=11, vol=0.015)
    out = STRATEGIES[key].run(df, RELAXED.get(key))
    assert out.entry.sum() > 0, f"{key} nunca gerou entrada"
    assert out.exit.sum() > 0, f"{key} nunca gerou saída"


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_no_lookahead(key, ohlcv):
    """O sinal da barra i não pode mudar quando barras futuras são adicionadas."""
    full = STRATEGIES[key].run(ohlcv)
    for cut in (700, 1100, 1400):
        partial = STRATEGIES[key].run(ohlcv.iloc[:cut].copy())
        assert (partial.entry.values == full.entry.values[:cut]).all(), f"{key}: entrada depende do futuro"
        assert (partial.exit.values == full.exit.values[:cut]).all(), f"{key}: saída depende do futuro"


def test_resolve_params_clamps_and_defaults():
    s = STRATEGIES["confluence"]
    p = s.resolve_params({"ema_fast": "8", "min_score": 99, "unknown": 1})
    assert p["ema_fast"] == 8
    assert p["min_score"] == 5  # limitado ao máximo
    assert p["exit_on_supertrend"] is True  # padrão
    assert "unknown" not in p
    assert p["ema_slow"] == 21  # padrão


def test_fast_slow_pairs_are_ordered():
    p = STRATEGIES["confluence"].resolve_params({"ema_fast": 30, "ema_slow": 10})
    assert (p["ema_fast"], p["ema_slow"]) == (10, 30)
    p = STRATEGIES["ema_cross"].resolve_params({"fast": 21, "slow": 21})
    assert p["fast"] < p["slow"]


def test_describe_is_serializable():
    import json

    for s in STRATEGIES.values():
        json.dumps(s.describe())
