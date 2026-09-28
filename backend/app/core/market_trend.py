"""Tendência do mercado: só comprar quando o Bitcoin está em alta.

Quando o Bitcoin cai, quase todas as moedas caem junto. O filtro olha o último
candle diário FECHADO do Bitcoin e só libera compras se ele fechou acima da
média (EMA) de N dias. O mesmo cálculo vale no backtest (alinhado a cada candle,
sem olhar o futuro) e no robô ao vivo.

Pesquisa (set/2026, taxa real de 0,4%, 14 moedas, escolha do robô num período e
medição no seguinte): nos robôs de 4h e diário, a média de 100 dias deixou o
resultado positivo nos dois grupos de moedas (+1,6% e +2,4% por período, contra
+5,5% e -3,1% sem o filtro).
"""

import logging
import threading
import time

import numpy as np
import pandas as pd

from app.core import indicators as ta

log = logging.getLogger("bot_trader.market_trend")

BTC = "BTCUSDT"
HISTORY_DAYS = 2200  # ~6 anos: cobre os testes mais longos (a IA do robô usa até 1.500 dias no diário) com folga para a média
_TTL = 3600  # o candle diário só muda uma vez por dia
_cache: dict[int, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def _history() -> pd.DataFrame:
    """Candles diários fechados do Bitcoin (guardados no banco; só busca na OKX o que falta)."""
    from app.services import backtesting  # evita import circular

    return backtesting.history(BTC, "1d", HISTORY_DAYS)


def _btc_daily(days: int) -> pd.DataFrame:
    """Diário do Bitcoin com o estado da tendência (em cache por 1 h)."""
    with _lock:
        hit = _cache.get(days)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    df = _history()
    ema = ta.ema(df["close"], days)
    out = pd.DataFrame({"close_time": df["close_time"].astype("int64"), "close": df["close"], "ema": ema, "ok": df["close"] > ema})
    with _lock:
        _cache[days] = (time.time(), out)
    return out


def aligned(df: pd.DataFrame, days: int, btc: pd.DataFrame | None = None) -> np.ndarray | None:
    """True onde, no fechamento de cada candle, o último diário fechado do Bitcoin estava acima da média de N dias.
    None se não der para ler o Bitcoin (aí o filtro não bloqueia, como no robô ao vivo)."""
    if btc is None:
        try:
            btc = _btc_daily(days)
        except Exception as exc:
            log.warning("Tendência do Bitcoin indisponível no teste: %s", exc)
            return None
    left = pd.DataFrame({"t": df["close_time"].astype("int64").to_numpy()})
    ref = pd.DataFrame({"t": btc["close_time"].astype("int64").to_numpy(), "ok": btc["ok"].to_numpy(dtype=bool)})
    merged = pd.merge_asof(left, ref, on="t", direction="backward")
    return merged["ok"].fillna(False).to_numpy(dtype=bool)


def live_check(days: int) -> tuple[bool, str, dict | None]:
    """(pode comprar?, motivo do bloqueio, leitura para a tela). Sem dados do Bitcoin, não bloqueia."""
    try:
        btc = _btc_daily(days)
    except Exception as exc:
        log.warning("Tendência do Bitcoin indisponível: %s", exc)
        return True, "", None
    last = btc.iloc[-1]
    info = {"days": days, "close": round(float(last["close"]), 2), "ema": round(float(last["ema"]), 2), "ok": bool(last["ok"])}
    if info["ok"]:
        return True, "", info
    return False, f"Bitcoin abaixo da média de {days} dias (mercado em baixa)", info


def clear_cache() -> None:
    with _lock:
        _cache.clear()
