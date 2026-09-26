import pandas as pd
import numpy as np
from tinydb import TinyDB, Query

# —————————————————————————————————————————————————————————————————————————
# CONFIGURAÇÃO DO BANCO TinyDB PARA ARMAZENAR LOCKS E FLAGS POR ATIVO
# Em modo de backtest intensivo, podemos usar apenas memória (sem I/O no disco)
# —————————————————————————————————————————————————————————————————————————

DB_PATH = "src/database/strategies_db.json"  # arquivo JSON onde TinyDB irá persistir os estados
TABLE_NAME = "chilo_rsi_data"

# Se True, todas as leituras/gravações são feitas num dicionário em RAM, sem tocar no JSON
USE_IN_MEMORY_ONLY = False

# Estrutura em memória para armazenar {asset: {asset, rsi_lock, position_rsi_70, rsi_over_80}}
_in_memory_states = {}


def get_asset_state(asset: str) -> dict:
    """
    Retorna o estado atual (rsi_lock, position_rsi_70, rsi_over_80) do ativo na tabela "chilo_rsi_data".
    Se USE_IN_MEMORY_ONLY=True, usa somente o dicionário em RAM. Caso contrário, lê/grava no TinyDB.
    Caso não exista, cria um documento padrão com todos os flags False.
    """
    if USE_IN_MEMORY_ONLY:
        # Se não existir em memória, inicializa com valores padrão
        return _in_memory_states.setdefault(
            asset, {"asset": asset, "rsi_lock": False, "position_rsi_70": False, "rsi_over_80": False}
        )

    # Modo normal: TinyDB em disco
    db = TinyDB(DB_PATH)
    table = db.table(TABLE_NAME)
    Assets = Query()
    results = table.search(Assets.asset == asset)
    if not results:
        # Se não existir, insere valores padrão
        default = {"asset": asset, "rsi_lock": False, "position_rsi_70": False, "rsi_over_80": False}
        table.insert(default)
        db.close()
        return default

    state = results[0]
    db.close()
    # Se algum campo estiver faltando (por mudança de versão), garante que existam:
    for key in ["rsi_lock", "position_rsi_70", "rsi_over_80"]:
        if key not in state:
            state[key] = False
    return state


def update_asset_state(asset: str, **kwargs):
    """
    Atualiza somente os campos fornecidos em kwargs para o documento do ativo na tabela "chilo_rsi_data".
    Se USE_IN_MEMORY_ONLY=True, atualiza apenas o dicionário em RAM. Caso contrário, grava no TinyDB.
    Exemplo: update_asset_state("BTCUSDT", rsi_lock=True, rsi_over_80=False)
    """
    if USE_IN_MEMORY_ONLY:
        state = _in_memory_states.setdefault(
            asset, {"asset": asset, "rsi_lock": False, "position_rsi_70": False, "rsi_over_80": False}
        )
        state.update(kwargs)
        return

    # Modo normal: TinyDB em disco
    db = TinyDB(DB_PATH)
    table = db.table(TABLE_NAME)
    Assets = Query()
    table.update(kwargs, Assets.asset == asset)
    db.close()


# —————————————————————————————————————————————————————————————————————————
# CÁLCULO DE RSI E MÉDIA MÓVEL DO RSI
# —————————————————————————————————————————————————————————————————————————


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula o RSI padrão (14 por default) usando o método Wilder (EMA de ganhos/perdas).
    Retorna uma Series de RSI alinhada com o índice original.
    """
    delta = series.diff()

    # Separa ganhos e perdas
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Usa EMA (Wilder) para médias de ganhos e perdas
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_rsi_sma(rsi_series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula a média móvel simples de período `period` sobre a série de RSI.
    Retorna uma Series alinhada com o índice original.
    """
    return rsi_series.rolling(window=period, min_periods=period).mean()


# —————————————————————————————————————————————————————————————————————————
# CÁLCULO DE ATR (Average True Range) PARA FILTRO DE VOLATILIDADE
# —————————————————————————————————————————————————————————————————————————


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula o ATR (Average True Range) padrão com período definido.
    Retorna uma Series de ATR alinhada ao índice original.
    """
    # True Range componentes
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


# —————————————————————————————————————————————————————————————————————————
# WRAPPER PARA A FUNÇÃO getChiloStrategy (já fornecida), ADAPTADA PARA RECEBER stock_data COM colunas
# 'high_price', 'low_price', 'close_price'
# —————————————————————————————————————————————————————————————————————————


def get_chilo_signal(
    stock_data: pd.DataFrame,
    length: int = 34,
    offset: int = 0,
    hilo_type: str = "HiLo",
    ma_type: str = "SMA",
    verbose: bool = False,
) -> bool:
    """
    Retorna True para sinal de COMPRA pelo HiLo, ou False para VENDA.
    Se dados insuficientes, retorna False.
    (Mesma lógica do getChiloStrategy fornecido, adaptado para 'high_price', 'low_price', 'close_price'.)
    """
    df = stock_data.copy()
    min_required = length + offset + 1
    if len(df) < min_required:
        if verbose:
            print("⚠️ HiLo: Dados insuficientes. Retornando False.")
        return False

    # Cálculo das médias de High e Low (HiLo)
    if ma_type.upper() == "EMA":
        hima = df["high_price"].ewm(span=length, adjust=False).mean()
        loma = df["low_price"].ewm(span=length, adjust=False).mean()
    else:
        hima = df["high_price"].rolling(window=length).mean()
        loma = df["low_price"].rolling(window=length).mean()

    simple_hilo = hilo_type == "HiLo"

    if not simple_hilo:
        hihi = df["high_price"].rolling(window=length).max()
        lolo = df["low_price"].rolling(window=length).min()
    else:
        hihi = lolo = pd.Series(np.nan, index=df.index)

    hilo = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        if i < length + offset:
            hilo.iat[i] = np.nan
            continue

        close_i = df["close_price"].iat[i]
        hima_off = hima.iat[i - offset]
        loma_off = loma.iat[i - offset]

        if simple_hilo:
            if close_i < loma_off:
                hilo_val = hima.iat[i]
            elif close_i > hima_off:
                hilo_val = loma.iat[i]
            else:
                hilo_val = hilo.iat[i - 1]
        else:
            if close_i < loma_off:
                hilo_val = hihi.iat[i]
            elif close_i > hima_off:
                hilo_val = lolo.iat[i]
            else:
                hilo_val = hilo.iat[i - 1]
        hilo.iat[i] = hilo_val

    # Determina sinais de compra e venda baseados em cruzamentos do preço sobre HiLo
    buy_arith = np.sign(df["close_price"] - hima.shift(offset))
    sell_arith = np.sign(df["close_price"] - loma.shift(offset))
    buy = (buy_arith.shift(1) <= 0.5) & (buy_arith > 0.5)
    sell = (sell_arith.shift(1) >= -0.5) & (sell_arith < -0.5)

    buy_state = pd.Series(False, index=df.index)
    for i in range(1, len(df)):
        if buy.iat[i]:
            buy_state.iat[i] = True
        elif sell.iat[i]:
            buy_state.iat[i] = False
        else:
            buy_state.iat[i] = buy_state.iat[i - 1]

    chilo_decision = bool(buy_state.iat[-1])
    if verbose:
        last_hima = hima.iat[-1]
        last_loma = loma.iat[-1]
        last_hilo = hilo.iat[-1]
        print("-------")
        print("📊 HiLo Strategy:")
        print(f" | Última HiMA: {last_hima:.3f}")
        print(f" | Última LoMA: {last_loma:.3f}")
        print(f" | Último HiLo: {last_hilo:.3f}")
        print(f" | Decisão HiLo: {'Comprar' if chilo_decision else 'Vender'}")
        print("-------\n")
    return chilo_decision


# —————————————————————————————————————————————————————————————————————————
# FUNÇÃO PRINCIPAL REFINADA: ChiloRSIStrategy COM PARÂMETROS CONFIGURÁVEIS
# —————————————————————————————————————————————————————————————————————————


def ChiloRSIStrategy(
    self,
    stock_data: pd.DataFrame,
    verbose: bool = True,
    # RSI
    rsi_period: int = 14,
    rsi_sma_period: int = 21,
    rsi_buy_max: float = 70.0,
    rsi_overbought: float = 80.0,
    rsi_reentry: float = 65.0,
    # HiLo
    hilo_length: int = 34,
    hilo_offset: int = 0,
    hilo_type: str = "HiLo",
    hilo_ma_type: str = "SMA",
    # Tendência de médio prazo (EMA)
    ema_trend_length: int = 50,
    use_trend_filter: bool = True,
    # ATR (volatilidade)
    atr_period: int = 14,
    atr_min_pct: float = 0.01,  # ex.: 1% de volatilidade mínima
    atr_max_pct: float = 0.03,  # ex.: 3% de volatilidade máxima
    use_atr_filter: bool = True,
) -> bool:
    """
    Aplica a estratégia refinada: Chilo + RSI + filtros de tendência + volatilidade.
    Parâmetros ajustáveis via argumentos:
      - rsi_period, rsi_sma_period, rsi_buy_max, rsi_overbought, rsi_reentry
      - hilo_length, hilo_offset, hilo_type, hilo_ma_type
      - ema_trend_length, use_trend_filter
      - atr_period, atr_min_pct, atr_max_pct, use_atr_filter

    Lógica principal:
      1) Calcula RSI e RSI_SMA
      2) Obtém sinal HiLo
      3) Calcula EMA para filtro de tendência (opcional)
      4) Calcula ATR para filtro de volatilidade (opcional)
      5) Lê/atualiza flags no DB: rsi_lock, position_rsi_70, rsi_over_80
      6) Verifica condições de compra e venda refinadas
      7) Retorna True (comprar/manter comprado) ou False (vender/manter fora)
    """

    if verbose:
        print("\n------------------------------------")
        print(f"🔍 Executando ChiloRSIStrategy refinada para {self.operation_code}...\n")

    df = stock_data.copy()
    asset = self.operation_code

    # —————————————————————————————————————————————
    # 1) Calcula RSI e RSI_SMA
    # —————————————————————————————————————————————
    rsi = compute_rsi(df["close_price"], period=rsi_period)
    rsi_sma = compute_rsi_sma(rsi, period=rsi_sma_period)
    df = df.assign(rsi=rsi, rsi_sma=rsi_sma).dropna(subset=["rsi", "rsi_sma"])
    if len(df) < 1:
        if verbose:
            print("⚠️ Dados insuficientes para RSI. Retornando False.")
        return False

    last_rsi = df["rsi"].iat[-1]
    last_rsi_sma = df["rsi_sma"].iat[-1]

    # —————————————————————————————————————————————
    # 2) Obtém sinal HiLo
    # —————————————————————————————————————————————
    chilo_signal = get_chilo_signal(
        df, length=hilo_length, offset=hilo_offset, hilo_type=hilo_type, ma_type=hilo_ma_type, verbose=verbose
    )

    # —————————————————————————————————————————————
    # 3) Calcula filtro de tendência (EMA de fechamento)
    # —————————————————————————————————————————————
    if use_trend_filter:
        ema50_series = df["close_price"].ewm(span=ema_trend_length, adjust=False).mean()
        last_ema50 = ema50_series.iat[-1]
        cond_trend = df["close_price"].iat[-1] > last_ema50
    else:
        cond_trend = True  # sem filtro de tendência

    if verbose and use_trend_filter:
        print(
            f"📈 Tendência (EMA{ema_trend_length}): Preço atual = {df['close_price'].iat[-1]:.2f}, EMA = {last_ema50:.2f} → {'Alta' if cond_trend else 'Baixa'}\n"
        )

    # —————————————————————————————————————————————
    # 4) Calcula filtro de volatilidade (ATR normalizado)
    # —————————————————————————————————————————————
    if use_atr_filter:
        atr_series = compute_atr(df["high_price"], df["low_price"], df["close_price"], period=atr_period)
        last_atr = atr_series.iat[-1]
        last_price = df["close_price"].iat[-1]
        last_atr_pct = last_atr / last_price if last_price != 0 else 0.0
        cond_atr = atr_min_pct <= last_atr_pct <= atr_max_pct
    else:
        cond_atr = True  # sem filtro de volatilidade

    if verbose and use_atr_filter:
        print(
            f"🌪️ Volatilidade (ATR{atr_period}): ATR = {last_atr:.4f}, ATR% = {last_atr_pct:.4f} → {'OK' if cond_atr else 'Fora da faixa'}\n"
        )

    # —————————————————————————————————————————————
    # 5) Lê estados do DB e atualiza flags conforme RSI
    # —————————————————————————————————————————————
    state = get_asset_state(asset)
    rsi_lock = state["rsi_lock"]
    position_rsi_70 = state["position_rsi_70"]
    rsi_over_80 = state["rsi_over_80"]

    # 5.1) Se estivermos em posição e RSI cruzou acima do limite de overbought, marca rsi_over_80
    if self.actual_trade_position and (not rsi_over_80) and (last_rsi >= rsi_overbought):
        update_asset_state(asset, rsi_over_80=True)
        rsi_over_80 = True
        if verbose:
            print(f"⚙️ [{asset}] RSI cruzou ≥ {rsi_overbought}: marcando rsi_over_80 = True\n")

    # 5.2) Se rsi_lock está ativo e RSI caiu abaixo do nível de reentrada, libera lock
    if rsi_lock and (last_rsi < rsi_reentry):
        update_asset_state(asset, rsi_lock=False)
        rsi_lock = False
        if verbose:
            print(f"🔓 [{asset}] RSI abaixo de {rsi_reentry}: destravando rsi_lock.\n")

    # 5.3) Se estivermos em posição, e RSI cruzou ≥ (rsi_buy_max), marca position_rsi_70 para futura saída
    if self.actual_trade_position and (not position_rsi_70) and (last_rsi >= rsi_buy_max):
        update_asset_state(asset, position_rsi_70=True)
        position_rsi_70 = True
        if verbose:
            print(f"⚙️ [{asset}] RSI cruzou ≥ {rsi_buy_max} during posição: marcando position_rsi_70 = True\n")

    # —————————————————————————————————————————————
    # 6) Verifica condições de COMPRA e VENDA REFINADAS
    # —————————————————————————————————————————————

    # --- Condições de COMPRA (todas devem ser True)
    cond_chilo_buy = chilo_signal  # HiLo indica compra
    cond_rsi_lt_buy = last_rsi < rsi_buy_max  # RSI abaixo do limite de compra
    cond_rsi_gt_sma = last_rsi > last_rsi_sma  # RSI acima da sua média móvel
    cond_filtro_trend = cond_trend  # Filtro de tendência (opcional)
    cond_filtro_atr = cond_atr  # Filtro de volatilidade (opcional)
    cond_lock_off = not rsi_lock  # Lock de RSI deve estar liberado

    if verbose:
        print("Condições de COMPRA [E]:")
        print(f"{'🟢' if cond_chilo_buy else '🔴'} HiLo indicar COMPRA")
        print(f"{'🟢' if cond_rsi_lt_buy else '🔴'} RSI < {rsi_buy_max} (RSI atual = {last_rsi:.2f})")
        print(f"{'🟢' if cond_rsi_gt_sma else '🔴'} RSI > RSI_SMA (RSI_SMA = {last_rsi_sma:.2f})")
        if use_trend_filter:
            print(f"{'🟢' if cond_filtro_trend else '🔴'} Preço atual {'>' if cond_trend else '<='} EMA{ema_trend_length}")
        if use_atr_filter:
            print(
                f"{'🟢' if cond_filtro_atr else '🔴'} ATR% dentro de [{atr_min_pct:.2f}, {atr_max_pct:.2f}] (ATR% = {last_atr_pct:.4f})"
            )
        print(f"{'🟢' if cond_lock_off else '🔴'} rsi_lock liberado\n")

    buy_cond = all([cond_chilo_buy, cond_rsi_lt_buy, cond_rsi_gt_sma, cond_filtro_trend, cond_filtro_atr, cond_lock_off])

    # --- Condições de VENDA (qualquer uma True → vende)
    # 1) HiLo indica venda
    cond_chilo_sell = not chilo_signal

    # 2) Se RSI estava overbought e agora cruzou abaixo de RSI_SMA (pullback)
    cond_over80_pullback = rsi_over_80 and (last_rsi < last_rsi_sma)

    # 3) Se position_rsi_70 ativa e RSI caiu abaixo de rsi_reentry (ex: 65)
    cond_rsi70_drop = position_rsi_70 and (last_rsi < rsi_reentry)

    if verbose:
        print("Condições de VENDA [OU]:")
        print(f"{'🟢' if cond_chilo_sell else '🔴'} HiLo indicar VENDA")
        print(f"{'🟢' if cond_over80_pullback else '🔴'} RSI estava ≥ {rsi_overbought} e agora < RSI_SMA")
        print(f"{'🟢' if cond_rsi70_drop else '🔴'} position_rsi_70 ativa e RSI < {rsi_reentry} (RSI atual = {last_rsi:.2f})\n")

    sell_cond = any([cond_chilo_sell, cond_over80_pullback, cond_rsi70_drop])

    # —————————————————————————————————————————————
    # 7) Lógica de decisão final
    # —————————————————————————————————————————————
    trade_signal = self.actual_trade_position

    if self.actual_trade_position and sell_cond:
        # VENDA
        trade_signal = False

        # Ativa rsi_lock (se não estiver ativo) para evitar novas entradas imediatas
        if not rsi_lock:
            update_asset_state(asset, rsi_lock=True)
            if verbose:
                print(f"🔒 [{asset}] Venda detectada: ativando rsi_lock.\n")

        # Zera flags de posição
        if position_rsi_70:
            update_asset_state(asset, position_rsi_70=False)
            if verbose:
                print(f"⚙️ [{asset}] position_rsi_70 zerado após venda.\n")
        if rsi_over_80:
            update_asset_state(asset, rsi_over_80=False)
            if verbose:
                print(f"⚙️ [{asset}] rsi_over_80 zerado após venda.\n")

        if verbose:
            print(f"❌ [{asset}] Condições de VENDA atendidas. (RSI={last_rsi:.2f}, RSI_SMA={last_rsi_sma:.2f})\n")

    elif (not self.actual_trade_position) and buy_cond:
        # COMPRA
        trade_signal = True

        # Se no candle de compra o RSI já estiver ≥ rsi_buy_max, seta position_rsi_70
        if (last_rsi >= rsi_buy_max) and (not position_rsi_70):
            update_asset_state(asset, position_rsi_70=True)
            if verbose:
                print(f"⚙️ [{asset}] position_rsi_70 ativado (RSI {last_rsi:.2f} ≥ {rsi_buy_max} ao comprar).\n")

        if verbose:
            print(f"✅ [{asset}] Condições de COMPRA atendidas. (RSI={last_rsi:.2f}, RSI_SMA={last_rsi_sma:.2f})\n")

    else:
        # Mantém posição atual
        status = "comprado" if self.actual_trade_position else "fora"
        if verbose:
            print(f"ℹ️ [{asset}] Nenhuma condição estrita atendida. Mantendo posição atual: {status}.\n")

    if verbose:
        print("------------------------------------\n")

    return trade_signal
