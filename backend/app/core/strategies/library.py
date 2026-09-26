"""Biblioteca de estratégias (long-only, spot).

Evoluções das estratégias originais do projeto:
  - ChiloRSI            -> HiLoRsiStrategy (sem estado em disco, com filtros)
  - Médias móveis       -> EmaCrossStrategy (cruzamento "fresco" + tendência + ADX + volume)
  - UT Bot Alerts       -> SupertrendStrategy
  - RSI topos/fundos    -> BollingerReversionStrategy
Novas: Donchian (rompimento), MACD momentum e Confluência (combina 7 fatores).
"""

import numpy as np
import pandas as pd

from app.core import indicators as ta
from app.core.strategies.base import Param, Strategy, StrategyOutput, all_of, always, any_of

TREND_PARAM = Param("trend_ema", "EMA de tendência", "int", 200, 20, 400, 1, help="Só compra acima desta média")
USE_TREND_PARAM = Param("use_trend_filter", "Filtro de tendência", "bool", True)


def _trend_ok(df: pd.DataFrame, p: dict) -> tuple[pd.Series, pd.Series]:
    trend = ta.ema(df["close"], p["trend_ema"])
    ok = df["close"] > trend if p["use_trend_filter"] else always(df.index)
    return ok, trend


# ---------------------------------------------------------------------------


class ConfluenceStrategy(Strategy):
    key = "confluence"
    ordered = (("ema_fast", "ema_slow"),)
    name = "Confluência de tendência"
    style = "confluência"
    description = (
        "Só compra no início de uma tendência de alta confirmada: preço acima da EMA de tendência, "
        "EMA rápida cruzando a lenta há poucos candles e pelo menos N de 5 confirmações (Supertrend, "
        "MACD, RSI saudável, ADX com +DI dominante e volume). Sai quando a EMA rápida perde a lenta. "
        "Entrar cedo e sair só na reversão foi o que se mostrou mais consistente entre pares e períodos."
    )
    params = [
        Param("ema_fast", "EMA rápida", "int", 9, 3, 100, 1),
        Param("ema_slow", "EMA lenta", "int", 21, 5, 200, 1),
        TREND_PARAM,
        Param("fresh_bars", "Cruzamento há no máximo (barras)", "int", 10, 1, 60, 1, help="Evita entrar atrasado"),
        Param("min_score", "Confirmações mínimas (de 5)", "int", 4, 0, 5, 1),
        Param("rsi_max", "RSI máximo p/ compra", "float", 70, 55, 90, 1, help="Evita comprar sobrecomprado"),
        Param("adx_min", "ADX mínimo", "float", 20, 0, 50, 1),
        Param("st_period", "Supertrend período", "int", 10, 5, 50, 1),
        Param("st_mult", "Supertrend multiplicador", "float", 3.0, 1.0, 6.0, 0.1),
        Param("exit_on_supertrend", "Sair também se Supertrend virar e perder a EMA lenta", "bool", True),
    ]

    def compute(self, df, p):
        close, high, low = df["close"], df["high"], df["low"]
        trend = ta.ema(close, p["trend_ema"])
        fast, slow = ta.ema(close, p["ema_fast"]), ta.ema(close, p["ema_slow"])
        st_line, st_dir = ta.supertrend(high, low, close, p["st_period"], p["st_mult"])
        _, _, hist = ta.macd(close)
        r = ta.rsi(close, 14)
        adx, pdi, mdi = ta.adx(high, low, close, 14)
        vol_ok = ta.sma(df["volume"], 3) > ta.sma(df["volume"], 20)

        confirmations = {
            "Supertrend em alta": st_dir > 0,
            "Histograma MACD positivo": hist > 0,
            f"RSI entre 50 e {p['rsi_max']:g}": (r >= 50) & (r <= p["rsi_max"]),
            f"ADX ≥ {p['adx_min']:g} com +DI > -DI": (adx >= p["adx_min"]) & (pdi > mdi),
            "Volume recente acima da média": vol_ok,
        }
        score = sum(s.fillna(False).astype(int) for s in confirmations.values())
        since_cross = ta.bars_since(ta.crossed_above(fast, slow))

        entry_conditions = {
            "Preço acima da EMA de tendência": close > trend,
            "EMA rápida acima da lenta": fast > slow,
            f"Cruzamento há ≤ {p['fresh_bars']} barras": since_cross <= p["fresh_bars"],
            f"{p['min_score']}+ confirmações (de 5)": score >= p["min_score"],
            f"RSI ≤ {p['rsi_max']:g}": r <= p["rsi_max"],
        }
        entry_conditions.update({f"· {k}": v for k, v in confirmations.items()})  # informativo

        exit_conditions = {"EMA rápida abaixo da lenta": fast < slow}
        if p["exit_on_supertrend"]:
            exit_conditions["Supertrend em baixa e preço abaixo da EMA lenta"] = (st_dir < 0) & (close < slow)

        required = {k: v for k, v in entry_conditions.items() if not k.startswith("· ")}
        return StrategyOutput(
            entry=all_of(required),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays={f"EMA {p['ema_fast']}": fast, f"EMA {p['ema_slow']}": slow, f"EMA {p['trend_ema']}": trend, "Supertrend": st_line},
            values={"Confirmações": score.astype(float), "RSI": r, "ADX": adx, "MACD hist": hist},
        )


# ---------------------------------------------------------------------------


class HiLoRsiStrategy(Strategy):
    key = "hilo_rsi"
    name = "HiLo + RSI (ChiloRSI v2)"
    style = "tendência"
    description = (
        "Evolução da ChiloRSI que o bot usava. Entra logo após o HiLo virar para alta, com RSI acima "
        "da própria média e abaixo do limite, e filtros de tendência e volatilidade (ATR%). Sai quando "
        "o HiLo vira para baixa (e, opcionalmente, quando o RSI perde força depois de sobrecomprado). "
        "Sem estado em disco: o mesmo sinal no backtest e ao vivo. Rende melhor em 4h do que em 1h."
    )
    params = [
        Param("hilo_length", "HiLo período", "int", 55, 5, 150, 1),
        Param("hilo_ma", "HiLo média", "select", "sma", options=["sma", "ema"]),
        Param("fresh_bars", "Virada do HiLo há no máximo (barras)", "int", 3, 0, 50, 1, help="0 = sem limite"),
        Param("rsi_period", "RSI período", "int", 14, 5, 50, 1),
        Param("rsi_sma_period", "Média do RSI", "int", 21, 3, 60, 1),
        Param("rsi_buy_max", "RSI máximo p/ compra", "float", 70, 50, 90, 1),
        Param("use_rsi_exits", "Sair por perda de força do RSI", "bool", True),
        Param("rsi_overbought", "RSI sobrecomprado", "float", 80, 60, 95, 1),
        Param("rsi_exit_level", "Sai se RSI perder", "float", 65, 40, 90, 1, help="Após ter passado do RSI máximo"),
        Param("lookback", "Memória do RSI (barras)", "int", 10, 2, 50, 1),
        TREND_PARAM,
        USE_TREND_PARAM,
        Param("use_atr_filter", "Filtro de volatilidade", "bool", True),
        Param("atr_min_pct", "ATR% mínimo", "float", 0.4, 0.0, 10.0, 0.1),
        Param("atr_max_pct", "ATR% máximo", "float", 5.0, 0.5, 30.0, 0.1),
    ]

    def compute(self, df, p):
        close, high, low = df["close"], df["high"], df["low"]
        line, state = ta.hilo(high, low, close, p["hilo_length"], p["hilo_ma"])
        r = ta.rsi(close, p["rsi_period"])
        r_sma = ta.sma(r, p["rsi_sma_period"])
        trend_ok, trend = _trend_ok(df, p)
        atr_pct = ta.atr(high, low, close, 14) / close * 100
        atr_ok = (atr_pct >= p["atr_min_pct"]) & (atr_pct <= p["atr_max_pct"]) if p["use_atr_filter"] else always(df.index)
        since_flip = ta.bars_since((state > 0) & (state.shift(1) <= 0))

        entry_conditions = {
            "HiLo em alta": state > 0,
            f"RSI < {p['rsi_buy_max']:g}": r < p["rsi_buy_max"],
            "RSI acima da sua média": r > r_sma,
            "Preço acima da EMA de tendência": trend_ok,
            "Volatilidade (ATR%) na faixa": atr_ok,
        }
        if p["fresh_bars"] > 0:
            entry_conditions[f"Virada do HiLo há ≤ {p['fresh_bars']} barras"] = since_flip <= p["fresh_bars"]
        recent_max = r.rolling(p["lookback"], min_periods=1).max()
        exit_conditions = {"HiLo virou para baixa": state < 0}
        if p["use_rsi_exits"]:
            exit_conditions[f"RSI passou de {p['rsi_overbought']:g} e perdeu a média"] = (
                recent_max >= p["rsi_overbought"]
            ) & ta.crossed_below(r, r_sma)
            exit_conditions[f"RSI passou de {p['rsi_buy_max']:g} e caiu abaixo de {p['rsi_exit_level']:g}"] = (
                recent_max >= p["rsi_buy_max"]
            ) & ta.crossed_below(r, p["rsi_exit_level"])
        overlays = {"HiLo": line}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"RSI": r, "RSI média": r_sma, "ATR%": atr_pct},
        )


# ---------------------------------------------------------------------------


class EmaCrossStrategy(Strategy):
    key = "ema_cross"
    ordered = (("fast", "slow"),)
    name = "Cruzamento de EMAs + ADX"
    style = "tendência"
    description = (
        "Evolução das estratégias de médias móveis. Compra apenas cruzamentos recentes (evita entrar "
        "atrasado), com preço acima da EMA de tendência, ADX mostrando tendência e volume confirmando. "
        "Sai no cruzamento de baixa."
    )
    params = [
        Param("fast", "EMA rápida", "int", 9, 3, 100, 1),
        Param("slow", "EMA lenta", "int", 21, 5, 200, 1),
        TREND_PARAM,
        USE_TREND_PARAM,
        Param("adx_min", "ADX mínimo", "float", 18, 0, 50, 1, help="0 desativa"),
        Param("volume_mult", "Volume mínimo (x média)", "float", 1.0, 0, 5, 0.1, help="0 desativa"),
        Param("fresh_bars", "Cruzamento há no máximo (barras)", "int", 3, 0, 50, 1),
    ]

    def compute(self, df, p):
        close = df["close"]
        fast, slow = ta.ema(close, p["fast"]), ta.ema(close, p["slow"])
        adx, _, _ = ta.adx(df["high"], df["low"], close, 14)
        trend_ok, trend = _trend_ok(df, p)
        since = ta.bars_since(ta.crossed_above(fast, slow))
        vol_ok = (
            df["volume"] >= ta.sma(df["volume"], 20) * p["volume_mult"] if p["volume_mult"] > 0 else always(df.index)
        )
        entry_conditions = {
            "EMA rápida acima da lenta": fast > slow,
            f"Cruzamento há ≤ {p['fresh_bars']} barras": since <= p["fresh_bars"],
            "Preço acima da EMA de tendência": trend_ok,
            f"ADX ≥ {p['adx_min']:g}": adx >= p["adx_min"] if p["adx_min"] > 0 else always(df.index),
            "Volume confirma": vol_ok,
        }
        exit_conditions = {"EMA rápida abaixo da lenta": fast < slow}
        overlays = {f"EMA {p['fast']}": fast, f"EMA {p['slow']}": slow}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"ADX": adx, "Barras desde cruzamento": since.replace(np.inf, np.nan)},
        )


# ---------------------------------------------------------------------------


class SupertrendStrategy(Strategy):
    key = "supertrend"
    name = "Supertrend + EMA"
    style = "tendência"
    description = (
        "Evolução do UT Bot Alerts: usa o Supertrend (stop móvel por ATR) para definir a direção, com "
        "filtro de tendência e um teto de RSI para não comprar esticado. Sai quando o Supertrend vira."
    )
    params = [
        Param("atr_period", "ATR período", "int", 10, 5, 50, 1),
        Param("multiplier", "Multiplicador", "float", 3.0, 1.0, 6.0, 0.1),
        TREND_PARAM,
        USE_TREND_PARAM,
        Param("rsi_max", "RSI máximo p/ compra", "float", 75, 50, 95, 1),
        Param("max_bars_after_flip", "Entrar até N barras após virada", "int", 6, 0, 100, 1, help="0 = sem limite"),
    ]

    def compute(self, df, p):
        close = df["close"]
        line, direction = ta.supertrend(df["high"], df["low"], close, p["atr_period"], p["multiplier"])
        r = ta.rsi(close, 14)
        trend_ok, trend = _trend_ok(df, p)
        since_flip = ta.bars_since((direction > 0) & (direction.shift(1) < 0))
        entry_conditions = {
            "Supertrend em alta": direction > 0,
            "Preço acima da EMA de tendência": trend_ok,
            f"RSI < {p['rsi_max']:g}": r < p["rsi_max"],
        }
        if p["max_bars_after_flip"] > 0:
            entry_conditions[f"Virada há ≤ {p['max_bars_after_flip']} barras"] = since_flip <= p["max_bars_after_flip"]
        exit_conditions = {"Supertrend em baixa": direction < 0}
        overlays = {"Supertrend": line}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"RSI": r, "Direção": direction},
        )


# ---------------------------------------------------------------------------


class BollingerReversionStrategy(Strategy):
    key = "bb_reversion"
    name = "Reversão Bollinger + RSI"
    style = "reversão"
    description = (
        "Compra quedas exageradas dentro de uma tendência de alta: o preço fecha abaixo da banda "
        "inferior e volta para dentro dela com o RSI em sobrevenda. Vende na média central ou quando o "
        "RSI recupera. Funciona melhor em mercados laterais; o stop do risco é essencial aqui."
    )
    params = [
        Param("bb_period", "Bollinger período", "int", 20, 10, 60, 1),
        Param("bb_std", "Desvios padrão", "float", 2.0, 1.0, 3.5, 0.1),
        Param("rsi_period", "RSI período", "int", 14, 5, 30, 1),
        Param("rsi_entry", "RSI de sobrevenda", "float", 30, 10, 50, 1),
        Param("rsi_exit", "RSI de saída", "float", 65, 50, 90, 1),
        Param("lookback", "Sobrevenda nas últimas N barras", "int", 3, 1, 10, 1),
        TREND_PARAM,
        USE_TREND_PARAM,
    ]

    def compute(self, df, p):
        close = df["close"]
        mid, upper, lower = ta.bollinger(close, p["bb_period"], p["bb_std"])
        r = ta.rsi(close, p["rsi_period"])
        trend_ok, trend = _trend_ok(df, p)
        entry_conditions = {
            "Fechou de volta acima da banda inferior": (close > lower) & (close.shift(1) < lower.shift(1)),
            f"RSI ≤ {p['rsi_entry']:g} recentemente": r.rolling(p["lookback"], min_periods=1).min() <= p["rsi_entry"],
            "Preço acima da EMA de tendência": trend_ok,
        }
        exit_conditions = {
            "Preço atingiu a média central": close >= mid,
            f"RSI ≥ {p['rsi_exit']:g}": r >= p["rsi_exit"],
        }
        overlays = {"BB superior": upper, "BB média": mid, "BB inferior": lower}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"RSI": r, "%B": (close - lower) / (upper - lower)},
        )


# ---------------------------------------------------------------------------


class DonchianBreakoutStrategy(Strategy):
    key = "donchian_breakout"
    name = "Rompimento Donchian (Turtle)"
    style = "rompimento"
    description = (
        "Sistema clássico das Tartarugas: compra quando o preço fecha acima da máxima das últimas N "
        "barras (com volume e ADX confirmando) e sai quando perde a mínima das últimas M barras."
    )
    params = [
        Param("entry_period", "Máxima de N barras", "int", 20, 5, 100, 1),
        Param("exit_period", "Mínima de M barras", "int", 10, 3, 60, 1),
        Param("volume_mult", "Volume mínimo (x média)", "float", 1.2, 0, 5, 0.1, help="0 desativa"),
        Param("adx_min", "ADX mínimo", "float", 18, 0, 50, 1, help="0 desativa"),
        TREND_PARAM,
        USE_TREND_PARAM,
    ]

    def compute(self, df, p):
        close = df["close"]
        upper, _ = ta.donchian(df["high"], df["low"], p["entry_period"])
        _, lower = ta.donchian(df["high"], df["low"], p["exit_period"])
        upper_prev, lower_prev = upper.shift(1), lower.shift(1)
        adx, _, _ = ta.adx(df["high"], df["low"], close, 14)
        trend_ok, trend = _trend_ok(df, p)
        vol_ok = (
            df["volume"] >= ta.sma(df["volume"], 20) * p["volume_mult"] if p["volume_mult"] > 0 else always(df.index)
        )
        entry_conditions = {
            f"Fechou acima da máxima de {p['entry_period']} barras": close > upper_prev,
            "Volume confirma": vol_ok,
            f"ADX ≥ {p['adx_min']:g}": adx >= p["adx_min"] if p["adx_min"] > 0 else always(df.index),
            "Preço acima da EMA de tendência": trend_ok,
        }
        exit_conditions = {f"Fechou abaixo da mínima de {p['exit_period']} barras": close < lower_prev}
        overlays = {"Donchian topo": upper_prev, "Donchian saída": lower_prev}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"ADX": adx},
        )


# ---------------------------------------------------------------------------


class MacdMomentumStrategy(Strategy):
    key = "macd_momentum"
    ordered = (("fast", "slow"),)
    name = "Momentum MACD"
    style = "momentum"
    description = (
        "Compra quando o MACD cruza acima da linha de sinal (de preferência abaixo de zero, pegando "
        "o início do movimento) com o preço acima da EMA de tendência. Sai quando o MACD perde o sinal."
    )
    params = [
        Param("fast", "MACD rápida", "int", 12, 3, 50, 1),
        Param("slow", "MACD lenta", "int", 26, 10, 100, 1),
        Param("signal", "Linha de sinal", "int", 9, 3, 30, 1),
        Param("only_below_zero", "Só cruzamentos abaixo de zero", "bool", True),
        Param("fresh_bars", "Cruzamento há no máximo (barras)", "int", 4, 0, 20, 1),
        TREND_PARAM,
        USE_TREND_PARAM,
    ]

    def compute(self, df, p):
        close = df["close"]
        line, sig, hist = ta.macd(close, p["fast"], p["slow"], p["signal"])
        trend_ok, trend = _trend_ok(df, p)
        cross = ta.crossed_above(line, sig)
        since = ta.bars_since(cross)
        entry_conditions = {
            f"MACD cruzou o sinal há ≤ {p['fresh_bars']} barras": since <= p["fresh_bars"],
            "MACD acima do sinal": line > sig,
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["only_below_zero"]:
            below_zero_at_cross = (line.where(cross).ffill()) < 0
            entry_conditions["Cruzamento abaixo de zero"] = below_zero_at_cross
        exit_conditions = {"MACD abaixo do sinal": line < sig}
        overlays = {f"EMA {p['trend_ema']}": trend} if p["use_trend_filter"] else {}
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"MACD": line, "Sinal": sig, "Histograma": hist},
        )
