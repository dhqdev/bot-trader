import numpy as np
import pandas as pd

from app.core import indicators as ta


def test_rsi_bounds(ohlcv):
    r = ta.rsi(ohlcv["close"], 14).dropna()
    assert len(r) > 1000
    assert r.between(0, 100).all()


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert ta.rsi(up, 14).iloc[-1] == 100
    flat = pd.Series(np.ones(60))
    assert ta.rsi(flat, 14).iloc[-1] == 50


def test_atr_positive(ohlcv):
    a = ta.atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14).dropna()
    assert (a > 0).all()


def test_supertrend_follows_trend():
    n = 300
    close = pd.Series(np.concatenate([np.linspace(100, 200, n // 2), np.linspace(200, 100, n // 2)]))
    high, low = close * 1.005, close * 0.995
    _, direction = ta.supertrend(high, low, close, 10, 3.0)
    assert direction.iloc[n // 2 - 5] == 1  # subida
    assert direction.iloc[-1] == -1  # descida


def test_hilo_state_flips():
    close = pd.Series(np.concatenate([np.linspace(100, 150, 100), np.linspace(150, 90, 100)]))
    _, state = ta.hilo(close * 1.01, close * 0.99, close, 20)
    assert state.iloc[95] == 1
    assert state.iloc[-1] == -1


def test_bars_since():
    ev = pd.Series([False, True, False, False, True, False])
    assert list(ta.bars_since(ev)) == [np.inf, 0, 1, 2, 0, 1]


def test_crosses():
    a = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0])
    b = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0])
    assert list(ta.crossed_above(a, b)) == [False, False, True, False, False]
    assert list(ta.crossed_below(a, b)) == [False, False, False, False, True]
