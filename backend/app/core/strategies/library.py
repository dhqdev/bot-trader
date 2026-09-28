"""Biblioteca de estratégias (long-only, spot).

Seleção feita por backtest em 14 pares x 1h/4h x 3 períodos, com validação
fora da amostra (pares e período que não foram usados para escolher regras
e parâmetros). Ficaram as 6 com melhor resultado; Supertrend, Cruzamento de
EMAs, MACD e Reversão Bollinger foram removidas por desempenho fraco.

Novas (criadas nesta seleção): Squeeze, Candle de ignição e Momentum por
volatilidade. Mantidas: Confluência, Donchian e HiLo + RSI (evolução da
ChiloRSI original).
"""

import numpy as np
import pandas as pd

from app.core import indicators as ta
from app.core.strategies.base import Param, Strategy, StrategyOutput, all_of, always, any_of

TREND_PARAM = Param(
    "trend_ema", "EMA de tendência", "int", 200, 20, 400, 1,
    help="Média móvel longa que define se o mercado está em alta. Com o filtro ligado, só compra com o preço acima dela. 200 é o padrão do mercado.",
)  # fmt: skip
USE_TREND_PARAM = Param(
    "use_trend_filter", "Só comprar em tendência de alta (preço acima da EMA de tendência)", "bool", True,
    help="Desligar aumenta o número de operações, mas nos testes piorou o resultado em mercados de queda.",
)  # fmt: skip


def _trend_ok(df: pd.DataFrame, p: dict) -> tuple[pd.Series, pd.Series]:
    trend = ta.ema(df["close"], p["trend_ema"])
    ok = df["close"] > trend if p["use_trend_filter"] else always(df.index)
    return ok, trend


HTF_PARAM = Param(
    "htf_ema", "Tendência de fundo: EMA de N candles", "int", 0, 0, 3000, 1,
    help="Só compra com o preço acima de uma média bem longa e subindo, ou seja, a favor da tendência de vários dias. 0 = desligado. ≈ 4 dias: 1152 candles em 5m, 384 em 15m, 96 em 1h.",
)  # fmt: skip


def _htf_uptrend(close: pd.Series, bars: int) -> pd.Series:
    """Tendência de fundo: preço acima de uma EMA longa que está subindo."""
    slow = ta.ema(close, bars)
    return (close > slow) & (slow > slow.shift(12))


def _fresh(event: pd.Series, bars: int) -> pd.Series:
    """O evento aconteceu há no máximo `bars` candles (0 = neste candle)."""
    return ta.bars_since(event) <= bars


# ---------------------------------------------------------------------------
# NOVA 1


class SqueezeBreakoutStrategy(Strategy):
    key = "squeeze"
    name = "Squeeze: compressão e rompimento"
    style = "rompimento"
    description = (
        "Mercados alternam calmaria e explosão. A estratégia espera o preço ficar comprimido (as Bandas de "
        "Bollinger entram dentro do Canal de Keltner) por vários candles e compra quando a compressão se "
        "desfaz com momentum para cima, em tendência de alta. Sai quando o preço perde a média do canal. "
        "Foi a melhor nos testes, inclusive nos pares e períodos fora da amostra, e rende mais em 4h."
    )
    params = [
        Param("length", "Período das bandas", "int", 20, 10, 60, 1,
              help="Quantos candles as Bandas de Bollinger e o Canal de Keltner consideram. 20 é o clássico."),
        Param("bb_std", "Largura das Bandas de Bollinger (desvios)", "float", 2.0, 1.0, 3.5, 0.1,
              help="Quanto maior, mais largas as bandas e mais difícil caracterizar compressão."),
        Param("kc_mult", "Largura do Canal de Keltner (× ATR)", "float", 2.0, 1.0, 3.5, 0.1,
              help="Quanto maior, mais fácil as Bollinger ficarem dentro do canal, ou seja, mais compressões detectadas."),
        Param("min_squeeze", "Compressão mínima (candles)", "int", 8, 1, 40, 1,
              help="Por quantos candles seguidos o mercado precisa ter ficado comprimido. Mais candles = sinais mais raros e mais fortes."),
        Param("fresh_bars", "Entrar até N candles após o rompimento", "int", 3, 0, 20, 1,
              help="Evita comprar tarde: depois disso o sinal é ignorado."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
        Param("exit_mode", "Regra de saída", "select", "mid", options=["mid", "momentum"],
              labels=["Preço perde a média do canal", "Momentum fica negativo"],
              help="Nos testes, sair pela média do canal deu resultado melhor."),
    ]  # fmt: skip

    def compute(self, df, p):
        close, high, low = df["close"], df["high"], df["low"]
        n = p["length"]
        _, bb_up, bb_low = ta.bollinger(close, n, p["bb_std"])
        kc_mid = ta.ema(close, n)
        rng = ta.atr(high, low, close, n)
        kc_up, kc_low = kc_mid + p["kc_mult"] * rng, kc_mid - p["kc_mult"] * rng

        squeeze_on = (bb_up < kc_up) & (bb_low > kc_low)
        squeezed_before = squeeze_on.astype(float).rolling(p["min_squeeze"]).sum().shift(1) >= p["min_squeeze"]
        released = (~squeeze_on) & squeeze_on.shift(1, fill_value=False) & squeezed_before
        # momentum do TTM Squeeze: preço menos o centro entre o meio do Donchian e a SMA
        donchian_mid = (high.rolling(n).max() + low.rolling(n).min()) / 2
        momentum = close - (donchian_mid + ta.sma(close, n)) / 2
        trend_ok, trend = _trend_ok(df, p)
        squeeze_len = squeeze_on.astype(int).groupby((~squeeze_on).cumsum()).cumsum()

        entry_conditions = {
            f"Saiu de compressão de {p['min_squeeze']}+ candles há ≤ {p['fresh_bars']} candles": _fresh(released, p["fresh_bars"]),
            "Momentum positivo": momentum > 0,
            "Momentum crescendo": momentum > momentum.shift(1),
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        if p["exit_mode"] == "mid":
            exit_conditions = {"Preço abaixo da média do canal": close < kc_mid}
        else:
            exit_conditions = {"Momentum ficou negativo": (momentum < 0) & (momentum.shift(1) >= 0)}

        overlays = {"Keltner superior": kc_up, "Média do canal": kc_mid, "Bollinger superior": bb_up}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"Momentum": momentum, "Em compressão": squeeze_on.astype(float), "Candles comprimido": squeeze_len.astype(float)},
        )


# ---------------------------------------------------------------------------
# NOVA 2


class IgnitionStrategy(Strategy):
    key = "ignition"
    name = "Candle de ignição"
    style = "momentum"
    description = (
        "Compra no candle que 'acende' um movimento: alta forte (corpo bem maior que a volatilidade normal), "
        "volume bem acima da média e fechamento perto da máxima, em tendência de alta. Sai quando o preço "
        "perde a média curta. Teve a maior taxa de operações lucrativas nos testes de design e se manteve "
        "positiva fora da amostra; melhor em 4h."
    )
    params = [
        Param("atr_mult", "Tamanho mínimo do candle (× ATR)", "float", 1.5, 0.5, 4.0, 0.1,
              help="Corpo do candle (fechamento − abertura) comparado ao ATR, a variação média de um candle. 1,5 = candle 50% maior que o normal."),
        Param("vol_mult", "Volume mínimo (× média de 20 candles)", "float", 1.5, 1.0, 5.0, 0.1,
              help="Confirma que há dinheiro entrando de verdade. 1,5 = volume 50% acima da média."),
        Param("close_near_high", "Fechamento no topo do candle (%)", "float", 70, 50, 100, 5,
              help="Onde o candle fechou entre a mínima (0%) e a máxima (100%). 70 = fechou nos 30% de cima, sem devolver a alta."),
        Param("exit_ema", "Média de saída (EMA)", "int", 20, 5, 100, 1,
              help="Sai quando o preço fecha abaixo desta média. Menor = sai mais rápido; maior = segura mais a tendência."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
    ]  # fmt: skip

    def compute(self, df, p):
        close, high, low, open_, volume = df["close"], df["high"], df["low"], df["open"], df["volume"]
        prev_atr = ta.atr(high, low, close, 14).shift(1)
        body_ratio = (close - open_) / prev_atr
        vol_ratio = volume / ta.sma(volume, 20).shift(1)
        close_pos = (close - low) / (high - low).replace(0, np.nan) * 100
        exit_ema = ta.ema(close, p["exit_ema"])
        trend_ok, trend = _trend_ok(df, p)

        entry_conditions = {
            f"Candle de alta ≥ {p['atr_mult']:g}× ATR": body_ratio >= p["atr_mult"],
            f"Volume ≥ {p['vol_mult']:g}× a média": vol_ratio >= p["vol_mult"],
            f"Fechou nos {100 - p['close_near_high']:g}% superiores do candle": close_pos >= p["close_near_high"],
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        exit_conditions = {f"Preço abaixo da EMA {p['exit_ema']}": close < exit_ema}
        overlays = {f"EMA {p['exit_ema']} (saída)": exit_ema}
        if p["use_trend_filter"]:
            overlays[f"EMA {p['trend_ema']}"] = trend
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"Candle/ATR": body_ratio, "Volume/média": vol_ratio, "Fechamento no candle %": close_pos},
        )


# ---------------------------------------------------------------------------
# NOVA 3


class VolMomentumStrategy(Strategy):
    key = "vol_momentum"
    name = "Momentum ajustado à volatilidade"
    style = "momentum"
    description = (
        "Mede a força da alta recente descontando o 'barulho' normal do ativo: o retorno da janela dividido "
        "pela volatilidade esperada no mesmo período (um z-score). Compra quando essa força passa do mínimo "
        "e sai quando ela some. Funciona igual em moedas calmas e agitadas. Teve a maior taxa de acerto em "
        "4h, mas teve o maior drawdown das novas: prefira stop e tamanho de posição conservadores."
    )
    params = [
        Param("lookback", "Janela do momentum (candles)", "int", 30, 10, 200, 1,
              help="Período em que a alta é medida. 30 candles de 4h = 5 dias."),
        Param("z_entry", "Força mínima para comprar (z)", "float", 1.0, 0.0, 4.0, 0.05,
              help="1,0 = alta equivalente a 1 desvio padrão acima do normal. Maior = menos sinais e mais fortes."),
        Param("z_exit", "Vende quando a força cai abaixo de (z)", "float", 0.0, -2.0, 2.0, 0.05,
              help="0 = sai quando o retorno da janela deixa de ser positivo."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
    ]  # fmt: skip

    def compute(self, df, p):
        close = df["close"]
        n = p["lookback"]
        log_close = np.log(close)
        window_return = log_close - log_close.shift(n)
        expected_move = log_close.diff().rolling(n).std() * np.sqrt(n)
        z = window_return / expected_move.replace(0, np.nan)
        trend_ok, trend = _trend_ok(df, p)

        entry_conditions = {
            f"Força cruzou acima de {p['z_entry']:g}": ta.crossed_above(z, p["z_entry"]),
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        exit_conditions = {f"Força abaixo de {p['z_exit']:g}": z < p["z_exit"]}
        overlays = {f"EMA {p['trend_ema']}": trend} if p["use_trend_filter"] else {}
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"Força (z)": z, f"Retorno {n} candles %": (np.exp(window_return) - 1) * 100},
        )


# ---------------------------------------------------------------------------


class ConfluenceStrategy(Strategy):
    key = "confluence"
    ordered = (("ema_fast", "ema_slow"),)
    name = "Confluência de tendência"
    style = "tendência"
    description = (
        "Só compra no início de uma tendência de alta confirmada: preço acima da EMA de tendência, EMA rápida "
        "cruzando a lenta há poucos candles e pelo menos N de 5 confirmações (Supertrend, MACD, RSI saudável, "
        "ADX com +DI dominante e volume). Sai quando a EMA rápida perde a lenta ou o Supertrend vira."
    )
    params = [
        Param("ema_fast", "EMA rápida", "int", 9, 3, 100, 1,
              help="Média curta: reage rápido ao preço. Quando cruza acima da lenta, começa uma tendência de alta."),
        Param("ema_slow", "EMA lenta", "int", 21, 5, 200, 1,
              help="Média mais longa, de referência. Precisa ser maior que a rápida."),
        TREND_PARAM,
        HTF_PARAM,
        Param("fresh_bars", "Cruzamento há no máximo (candles)", "int", 10, 1, 60, 1,
              help="Só compra se o cruzamento das médias for recente, para não entrar no fim do movimento."),
        Param("min_score", "Confirmações mínimas (de 5)", "int", 4, 0, 5, 1,
              help="Quantos dos 5 indicadores de apoio precisam concordar. Mais = menos entradas e mais seletivas."),
        Param("rsi_max", "RSI máximo para comprar", "float", 70, 55, 90, 1,
              help="O RSI mede se o preço subiu demais em pouco tempo (0 a 100). Acima de 70 costuma estar 'esticado'."),
        Param("adx_min", "ADX mínimo", "float", 20, 0, 50, 1,
              help="O ADX mede a força da tendência (0 a 100). Abaixo de 20 o mercado costuma estar sem direção."),
        Param("st_period", "Supertrend: período do ATR", "int", 10, 5, 50, 1,
              help="Candles usados para medir a volatilidade do Supertrend."),
        Param("st_mult", "Supertrend: multiplicador", "float", 3.0, 1.0, 6.0, 0.1,
              help="Distância da linha do Supertrend ao preço. Maior = vira de lado menos vezes."),
        Param("exit_on_supertrend", "Sair também se o Supertrend virar e o preço perder a EMA lenta", "bool", True,
              help="Sai mais cedo quando a tendência enfraquece. Ligado deu resultado melhor nos testes."),
    ]  # fmt: skip

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
            f"Cruzamento há ≤ {p['fresh_bars']} candles": since_cross <= p["fresh_bars"],
            f"{p['min_score']}+ confirmações (de 5)": score >= p["min_score"],
            f"RSI ≤ {p['rsi_max']:g}": r <= p["rsi_max"],
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
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


class DonchianBreakoutStrategy(Strategy):
    key = "donchian_breakout"
    name = "Rompimento Donchian (Tartarugas)"
    style = "rompimento"
    description = (
        "O sistema clássico das Tartarugas: compra quando o preço fecha acima da máxima dos últimos N candles, "
        "com volume e ADX confirmando, e vende quando perde a mínima dos últimos M candles. Foi bem fora da "
        "amostra, mas com drawdown maior que as novas."
    )
    params = [
        Param("entry_period", "Rompe a máxima de N candles", "int", 20, 5, 100, 1,
              help="Compra quando o fechamento supera a maior máxima deste período (um topo recente)."),
        Param("exit_period", "Vende ao perder a mínima de M candles", "int", 10, 3, 60, 1,
              help="Menor que o de entrada, para proteger o lucro mais rápido."),
        Param("volume_mult", "Volume mínimo (× média)", "float", 1.2, 0, 5, 0.1,
              help="Rompimentos com pouco volume costumam falhar. 0 desliga o filtro."),
        Param("adx_min", "ADX mínimo", "float", 18, 0, 50, 1,
              help="Força mínima da tendência (0 a 100). 0 desliga o filtro."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
    ]  # fmt: skip

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
            f"Fechou acima da máxima de {p['entry_period']} candles": close > upper_prev,
            "Volume confirma": vol_ok,
            f"ADX ≥ {p['adx_min']:g}": adx >= p["adx_min"] if p["adx_min"] > 0 else always(df.index),
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        exit_conditions = {f"Fechou abaixo da mínima de {p['exit_period']} candles": close < lower_prev}
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


class HiLoRsiStrategy(Strategy):
    key = "hilo_rsi"
    name = "HiLo + RSI (ChiloRSI v2)"
    style = "tendência"
    description = (
        "Evolução da ChiloRSI que o bot antigo usava. Entra logo após o HiLo virar para alta, com RSI acima "
        "da própria média e abaixo do limite, e filtros de tendência e volatilidade (ATR%). Sai quando o HiLo "
        "vira para baixa ou o RSI perde força depois de sobrecomprado. Menor drawdown entre as de tendência; "
        "use em 4h."
    )
    params = [
        Param("hilo_length", "HiLo: período", "int", 55, 5, 150, 1,
              help="Candles das médias de máximas e mínimas. 55 foi bem melhor que o 34 original nos testes."),
        Param("hilo_ma", "HiLo: tipo de média", "select", "sma", options=["sma", "ema"],
              labels=["Simples (SMA)", "Exponencial (EMA)"], help="A exponencial reage mais rápido."),
        Param("fresh_bars", "Virada do HiLo há no máximo (candles)", "int", 3, 0, 50, 1,
              help="Evita entrar tarde. 0 = aceita a qualquer momento da alta."),
        Param("rsi_period", "RSI: período", "int", 14, 5, 50, 1, help="14 é o padrão."),
        Param("rsi_sma_period", "RSI: média do RSI", "int", 21, 3, 60, 1,
              help="Só compra com o RSI acima da própria média, ou seja, ganhando força."),
        Param("rsi_buy_max", "RSI máximo para comprar", "float", 70, 50, 90, 1,
              help="Acima disso o preço já subiu demais para entrar."),
        Param("use_rsi_exits", "Sair quando o RSI perde força depois de sobrecomprado", "bool", True,
              help="Realiza o lucro após uma alta forte, antes do HiLo virar."),
        Param("rsi_overbought", "RSI sobrecomprado", "float", 80, 60, 95, 1,
              help="Se o RSI passou deste nível e depois cai abaixo da própria média, vende."),
        Param("rsi_exit_level", "Vende se o RSI cair abaixo de", "float", 65, 40, 90, 1,
              help="Depois de o RSI ter passado do máximo para compra."),
        Param("lookback", "Memória do RSI (candles)", "int", 10, 2, 50, 1,
              help="Por quantos candles o sistema 'lembra' que o RSI ficou alto."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
        Param("use_atr_filter", "Filtro de volatilidade", "bool", True,
              help="Evita operar com o mercado parado demais ou nervoso demais."),
        Param("atr_min_pct", "Volatilidade mínima (ATR % do preço)", "float", 0.4, 0.0, 10.0, 0.1,
              help="Variação média por candle, em % do preço."),
        Param("atr_max_pct", "Volatilidade máxima (ATR % do preço)", "float", 5.0, 0.5, 30.0, 0.1,
              help="Acima disso o mercado está nervoso demais."),
    ]  # fmt: skip

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
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        if p["fresh_bars"] > 0:
            entry_conditions[f"Virada do HiLo há ≤ {p['fresh_bars']} candles"] = since_flip <= p["fresh_bars"]
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
# NÍVEL RÁPIDO (minutos)


class RsiBounceStrategy(Strategy):
    key = "rsi_bounce"
    name = "Repique do RSI (rápida)"
    style = "reversão"
    description = (
        "Feita para candles curtos (5m e 15m): compra quando o RSI curto sai de uma queda exagerada e vira "
        "para cima, com o preço acima da EMA de tendência e, opcionalmente, da tendência de fundo. Vende "
        "quando o RSI recupera. As operações duram minutos. Atenção: nos testes perdeu um pouco na maioria "
        "dos casos, porque as taxas consomem o ganho de movimentos tão curtos. Use no modo simulado."
    )
    params = [
        Param("rsi_period", "RSI: período", "int", 7, 2, 30, 1,
              help="RSI curto reage rápido. 7 candles de 5m = 35 minutos."),
        Param("level", "Compra quando o RSI estava abaixo de", "float", 20, 5, 40, 1,
              help="Nível de queda exagerada. Menor = sinais mais raros e quedas mais fortes."),
        Param("exit_level", "Vende quando o RSI passar de", "float", 60, 40, 90, 1,
              help="Nível de recuperação para realizar o ganho."),
        TREND_PARAM,
        USE_TREND_PARAM,
        HTF_PARAM,
    ]  # fmt: skip

    def compute(self, df, p):
        close, open_ = df["close"], df["open"]
        r = ta.rsi(close, p["rsi_period"])
        trend_ok, trend = _trend_ok(df, p)
        entry_conditions = {
            f"RSI estava abaixo de {p['level']:g}": r.shift(1) < p["level"],
            "RSI virou para cima": r > r.shift(1),
            "Candle de alta": close > open_,
            "Preço acima da EMA de tendência": trend_ok,
        }
        if p["htf_ema"] > 0:
            entry_conditions["Tendência de fundo em alta"] = _htf_uptrend(close, p["htf_ema"])
        exit_conditions = {f"RSI acima de {p['exit_level']:g}": r > p["exit_level"]}
        overlays = {f"EMA {p['trend_ema']}": trend} if p["use_trend_filter"] else {}
        if p["htf_ema"] > 0:
            overlays[f"Tendência de fundo (EMA {p['htf_ema']})"] = ta.ema(close, p["htf_ema"])
        return StrategyOutput(
            entry=all_of(entry_conditions),
            exit=any_of(exit_conditions),
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            overlays=overlays,
            values={"RSI": r},
        )
