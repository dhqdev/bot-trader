"""Índice de Medo e Ganância (Fear & Greed) do mercado cripto, da alternative.me.

Um valor por dia, de 0 (medo extremo) a 100 (ganância extrema), publicado às
00:00 UTC. É usado como filtro de entrada. Nos testes (set/2026, 14 pares,
3 períodos, taxa e slippage reais):
- evitar compras com medo extremo (índice <= 20) manteve ou melhorou o
  resultado de todas as estratégias de 4 h, com queda máxima menor;
- só comprar com o índice subindo na semana melhorou os candles de 1-2 h nos
  dois grupos de pares (ex.: Ignição 1h de +2,5% para +8,2% na mediana), mas
  piorou os de 4 h;
- evitar ganância alta e "só entre 25 e 75" deram resultados inconsistentes.
"""

import logging
import math
import threading
import time
from datetime import datetime, timezone

import httpx
import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db import session_scope
from app.models import FearGreed

log = logging.getLogger("bot_trader.sentiment")

FNG_URL = "https://api.alternative.me/fng/"
DAY_MS = 86_400_000
STALE_DAYS = 3  # sem valor novo há mais tempo que isso: o filtro não bloqueia nada

LABELS_PT = {
    "Extreme Fear": "Medo extremo",
    "Fear": "Medo",
    "Neutral": "Neutro",
    "Greed": "Ganância",
    "Extreme Greed": "Ganância extrema",
}

FILTER_LABELS = {
    "off": "desligado",
    "avoid_extreme_fear": "evita medo extremo",
    "rising": "só com sentimento subindo",
    "both": "evita medo extremo e só com sentimento subindo",
}


def label_pt(value: float | None) -> str:
    if value is None or math.isnan(value):
        return ""
    if value <= 24:
        return "Medo extremo"
    if value <= 45:
        return "Medo"
    if value <= 55:
        return "Neutro"
    if value <= 75:
        return "Ganância"
    return "Ganância extrema"


def fetch_fng(limit: int = 0) -> list[dict]:
    """Histórico do índice (limit=0 traz tudo, desde 2018)."""
    res = httpx.get(FNG_URL, params={"limit": limit, "format": "json"}, timeout=20, follow_redirects=True)
    res.raise_for_status()
    rows = res.json().get("data") or []
    out = []
    for r in rows:
        try:
            day = int(r["timestamp"]) * 1000
            out.append({"day": day - day % DAY_MS, "value": int(r["value"]), "label": str(r.get("value_classification", ""))})
        except (KeyError, TypeError, ValueError):
            continue
    return out


class SentimentStore:
    """Série diária guardada no banco, com cache em memória."""

    def __init__(self):
        self._lock = threading.Lock()
        self._series: pd.Series | None = None
        self._loaded_at = 0.0
        self.fetcher = fetch_fng  # ponto de injeção (testes)

    def refresh(self) -> int:
        """Baixa os valores novos e grava. Devolve quantos dias foram gravados."""
        with session_scope() as db:
            count = db.scalar(select(FearGreed.day).limit(1))
        rows = self.fetcher(0 if count is None else 30)
        with session_scope() as db:
            for r in rows:
                row = db.get(FearGreed, r["day"])
                if row is None:
                    db.add(FearGreed(day=r["day"], value=r["value"], label=r["label"]))
                else:
                    row.value, row.label = r["value"], r["label"]
        self.invalidate()
        return len(rows)

    def invalidate(self) -> None:
        with self._lock:
            self._series = None

    def series(self) -> pd.Series:
        with self._lock:
            if self._series is not None and time.time() - self._loaded_at < 600:
                return self._series
        with session_scope() as db:
            rows = db.execute(select(FearGreed.day, FearGreed.value).order_by(FearGreed.day)).all()
        s = pd.Series([float(v) for _, v in rows], index=[int(d) for d, _ in rows], dtype=float)
        with self._lock:
            self._series, self._loaded_at = s, time.time()
        return s

    def latest(self) -> dict | None:
        s = self.series()
        if s.empty:
            return None
        day, value = int(s.index[-1]), float(s.iloc[-1])
        week_ago = s[s.index <= day - 7 * DAY_MS]
        prev = float(week_ago.iloc[-1]) if not week_ago.empty else None
        age_days = (time.time() * 1000 - day) / DAY_MS
        return {
            "value": int(value),
            "label": label_pt(value),
            "day": datetime.fromtimestamp(day / 1000, tz=timezone.utc).date().isoformat(),
            "value_7d_ago": int(prev) if prev is not None else None,
            "change_7d": int(value - prev) if prev is not None else None,
            "stale": age_days > STALE_DAYS,
        }

    def history(self, days: int = 90) -> list[dict]:
        s = self.series().tail(days)
        return [
            {"date": datetime.fromtimestamp(int(d) / 1000, tz=timezone.utc).date().isoformat(), "value": int(v)}
            for d, v in s.items()
        ]

    def aligned(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
        """Valor conhecido no fechamento de cada candle e o de 7 dias antes (sem olhar o futuro)."""
        s = self.series()
        if s.empty or df.empty:
            return None
        fng = pd.DataFrame({"ts": s.index.astype("int64"), "fng": s.to_numpy(dtype=float)})
        closes = df["close_time"].astype("int64")

        def lookup(times: pd.Series) -> np.ndarray:
            left = pd.DataFrame({"t": times.to_numpy(dtype="int64")})
            m = pd.merge_asof(left, fng, left_on="t", right_on="ts", direction="backward", tolerance=STALE_DAYS * DAY_MS)
            return m["fng"].to_numpy(dtype=float)

        return lookup(closes), lookup(closes - 7 * DAY_MS)


sentiment = SentimentStore()


def entry_mask(mode: str, now: np.ndarray, week_ago: np.ndarray, fear_threshold: float) -> np.ndarray:
    """True onde o filtro deixa comprar. Sem dado (NaN) nunca bloqueia."""
    ok = np.ones(len(now), dtype=bool)
    if mode in ("avoid_extreme_fear", "both"):
        ok &= np.isnan(now) | (now > fear_threshold)
    if mode in ("rising", "both"):
        ok &= np.isnan(now) | np.isnan(week_ago) | (now >= week_ago)
    return ok


def live_check(mode: str, fear_threshold: float) -> tuple[bool, str, dict | None]:
    """(pode comprar?, motivo do bloqueio, leitura atual) para o motor ao vivo."""
    info = sentiment.latest()
    if mode == "off" or info is None or info["stale"]:
        return True, "", info
    value, prev = info["value"], info["value_7d_ago"]
    if mode in ("avoid_extreme_fear", "both") and value <= fear_threshold:
        return False, f"medo extremo no mercado (índice de medo e ganância em {value}, limite {int(fear_threshold)})", info
    if mode in ("rising", "both") and prev is not None and value < prev:
        return False, f"sentimento do mercado caindo na semana (índice {prev} → {value})", info
    return True, "", info
