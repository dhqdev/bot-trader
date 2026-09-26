"""Indicadores técnicos vetorizados.

Todas as funções são causais: o valor na barra `i` depende apenas das
barras `<= i`. Isso garante que o backtest e a operação real enxergam
exatamente os mesmos sinais (testado em tests/test_strategies.py).
"""

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Média de Wilder (usada em RSI, ATR e ADX)."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma(-delta.clip(upper=0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + gain / loss)  # loss = 0 -> RSI 100
    return out.mask((gain == 0) & (loss == 0), 50.0)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return rma(true_range(high, low, close), n)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (ADX, +DI, -DI)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = rma(true_range(high, low, close), n)
    plus_di = 100 * rma(plus_dm, n) / tr
    minus_di = 100 * rma(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx, n), plus_di, minus_di


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (meio, banda superior, banda inferior)."""
    mid = sma(close, n)
    std = close.rolling(n, min_periods=n).std(ddof=0)
    return mid, mid + k * std, mid - k * std


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (linha MACD, sinal, histograma)."""
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    line = line.where(close.notna().cumsum() >= slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, mult: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """Retorna (linha do Supertrend, direção) com direção 1 = alta, -1 = baixa."""
    a = atr(high, low, close, n).to_numpy()
    h, l, c = high.to_numpy(), low.to_numpy(), close.to_numpy()
    hl2 = (h + l) / 2
    upper_basic = hl2 + mult * a
    lower_basic = hl2 - mult * a

    size = len(c)
    upper = np.full(size, np.nan)
    lower = np.full(size, np.nan)
    direction = np.zeros(size)
    line = np.full(size, np.nan)

    for i in range(size):
        if np.isnan(a[i]):
            continue
        if i == 0 or np.isnan(upper[i - 1]):
            upper[i], lower[i] = upper_basic[i], lower_basic[i]
            direction[i] = 1 if c[i] >= hl2[i] else -1
        else:
            upper[i] = upper_basic[i] if (upper_basic[i] < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
            lower[i] = lower_basic[i] if (lower_basic[i] > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
            prev = direction[i - 1]
            if prev == -1 and c[i] > upper[i - 1]:
                direction[i] = 1
            elif prev == 1 and c[i] < lower[i - 1]:
                direction[i] = -1
            else:
                direction[i] = prev
        line[i] = lower[i] if direction[i] == 1 else upper[i]

    return pd.Series(line, index=close.index), pd.Series(direction, index=close.index)


def donchian(high: pd.Series, low: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    """Retorna (máxima de n barras, mínima de n barras), incluindo a barra atual."""
    return high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()


def hilo(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 34, ma: str = "sma") -> tuple[pd.Series, pd.Series]:
    """HiLo Activator. Retorna (linha, estado) com estado 1 = alta, -1 = baixa.

    Vira para alta quando o fechamento supera a média das máximas e para
    baixa quando perde a média das mínimas (mesma regra do ChiloRSI antigo).
    """
    avg = ema if ma.lower() == "ema" else sma
    hi_ma, lo_ma = avg(high, n), avg(low, n)
    raw = pd.Series(np.nan, index=close.index)
    raw[close > hi_ma] = 1.0
    raw[close < lo_ma] = -1.0
    state = raw.ffill().fillna(0.0)
    line = pd.Series(np.where(state > 0, lo_ma, hi_ma), index=close.index)
    return line, state


def crossed_above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    return ((a > b) & (a.shift(1) <= b_prev)).fillna(False)


def crossed_below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    return ((a < b) & (a.shift(1) >= b_prev)).fillna(False)


def bars_since(event: pd.Series) -> pd.Series:
    """Número de barras desde a última ocorrência de `event` (0 na própria barra)."""
    event = event.fillna(False).astype(bool)
    groups = event.cumsum()
    counts = groups.groupby(groups).cumcount().astype(float)
    counts[groups == 0] = np.inf
    return counts
