import pytest

from app.core.strategies import PREVIOUS_DEFAULTS, STRATEGIES

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


RELAXED: dict = {}  # parâmetros mais soltos para estratégias seletivas demais nos dados sintéticos


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
    p = STRATEGIES["confluence"].resolve_params({"ema_fast": 21, "ema_slow": 21})
    assert p["ema_fast"] < p["ema_slow"]


def test_removed_strategies_resolve_to_replacement():
    from app.core.strategies import REMOVED, get_strategy

    for old, new in REMOVED.items():
        assert get_strategy(old).key == new


def test_describe_is_serializable():
    import json

    for s in STRATEGIES.values():
        json.dumps(s.describe())


def test_profiles_are_valid():
    from app.core.exchange import INTERVAL_MINUTES
    from app.core.profiles import PROFILES, TIERS, profiles_payload, tier_of

    assert [t["key"] for t in TIERS] == ["rapido", "medio", "lento"]
    payload = profiles_payload()
    for tier in payload["tiers"]:
        assert len(tier["profiles"]) >= 2
        for prof in tier["profiles"]:
            assert prof["interval"] in INTERVAL_MINUTES
            assert tier_of(prof["interval"]) == tier["key"]
            assert prof["strategy"] in STRATEGIES
            assert prof["risk"]["stop_loss_mode"] in ("atr", "percent")
    assert sum(1 for p in PROFILES if p.get("recommended")) == 1


def test_htf_filter_only_restricts_entries(ohlcv):
    base = STRATEGIES["ignition"].run(ohlcv)
    filtered = STRATEGIES["ignition"].run(ohlcv, {"htf_ema": 300})
    assert not (filtered.entry & ~base.entry).any()  # o filtro só remove entradas
    assert (filtered.exit == base.exit).all()


@pytest.mark.parametrize("key", list(PREVIOUS_DEFAULTS))
def test_looser_defaults_only_add_entries(key):
    """Os padrões novos compram em tudo que os antigos compravam, e em mais candles."""
    df = make_ohlcv(3000, seed=11, vol=0.015)
    old = STRATEGIES[key].run(df, PREVIOUS_DEFAULTS[key]).entry
    new = STRATEGIES[key].run(df).entry
    assert not (old & ~new).any()
    assert new.sum() > old.sum()


def test_vol_momentum_without_window_buys_only_on_the_cross(ohlcv):
    from app.core import indicators as ta

    out = STRATEGIES["vol_momentum"].run(ohlcv, {"fresh_bars": 0, "use_trend_filter": False})
    z = out.values["Força (z)"]
    assert (out.entry == ta.crossed_above(z, 1.0)).all()
    later = STRATEGIES["vol_momentum"].run(ohlcv, {"fresh_bars": 8, "use_trend_filter": False})
    assert (z[later.entry] >= 1.0).all()  # na janela, só compra se a força continua acima do mínimo
