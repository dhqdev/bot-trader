import os
import tempfile
from pathlib import Path

# Configuração isolada ANTES de importar o app (settings e engine são criados no import)
_tmp = Path(tempfile.mkdtemp(prefix="bt-tests-"))
os.environ["BT_DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["BT_SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["BT_ENGINE_AUTOSTART"] = "false"
os.environ["BT_ANTHROPIC_API_KEY"] = ""

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from app.core.exchange import SymbolRules, interval_ms, now_ms  # noqa: E402
from app.db import init_db  # noqa: E402

init_db()


def make_ohlcv(n: int = 1500, seed: int = 7, drift: float = 0.0002, vol: float = 0.01, interval: str = "1h") -> pd.DataFrame:
    """Série sintética com regimes de tendência, terminando no último candle fechado."""
    rng = np.random.default_rng(seed)
    regime = np.sin(np.linspace(0, 12, n)) * 0.002
    rets = rng.normal(drift, vol, n) + regime
    close = 100 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    spread = np.abs(rng.normal(0, vol / 2, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.lognormal(10, 0.5, n)
    step = interval_ms(interval)
    last_closed = (now_ms() // step) * step - step
    times = last_closed - (n - 1 - np.arange(n)) * step
    return pd.DataFrame(
        {
            "time": times.astype("int64"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time": (times + step - 1).astype("int64"),
        }
    )


class FakeMarket:
    """Mercado controlado para testar o motor sem rede."""

    def __init__(self, df: pd.DataFrame | None = None):
        self.df = df if df is not None else make_ohlcv()
        self.current = float(self.df["close"].iloc[-1])

    def klines(self, symbol, interval, limit=500, closed_only=True):
        return self.df.tail(limit).reset_index(drop=True)

    def price(self, symbol):
        return self.current

    def prices(self):
        return {"SOLUSDT": self.current}

    def ticker_24h(self, symbol):
        return {"price": self.current, "change_pct": 0.0, "high": self.current, "low": self.current, "quote_volume": 1e6}

    def symbol_rules(self, symbol):
        return SymbolRules(symbol, "SOL", "USDT", tick_size=0.01, step_size=0.001, min_qty=0.001, min_notional=5.0)

    def symbols(self, quote=None):
        return [{"symbol": "SOLUSDT", "base": "SOL", "quote": "USDT"}]


@pytest.fixture
def ohlcv():
    return make_ohlcv()


@pytest.fixture
def fake_market():
    return FakeMarket()


@pytest.fixture(scope="module")
def fresh_db():
    """Banco zerado para módulos que testam o fluxo de cadastro (primeiro usuário)."""
    from app.db import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
