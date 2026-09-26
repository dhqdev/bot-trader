import pandas as pd
import numpy as np

import os
import sys
import json
from datetime import datetime

# Configuração de caminhos para importações
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Adicionar diretórios ao sys.path
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)

class Indicators:
    """
    Classe que fornece acesso centralizado a todos os indicadores técnicos.
    """
    
    @staticmethod
    def getRSI(data, window=14, period=None, last_only=True):
        """
        Calcula o Relative Strength Index (RSI)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - window: Período para cálculo do RSI
        - period: Período alternativo (mantido para compatibilidade)
        - last_only: Se True, retorna apenas o último valor
        
        Retorno:
        - Série com os valores do RSI
        """
        actual_window = period if period is not None else window
        close_col = 'close' if 'close' in data.columns else data.columns[0]
        series = data[close_col]
        
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=actual_window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=actual_window).mean()
        
        # Evitar divisão por zero
        rs = gain / loss.replace(0, np.finfo(float).eps)
        rsi_values = 100 - (100 / (1 + rs))
        
        return rsi_values.iloc[-1] if last_only else rsi_values

    @staticmethod
    def getMACD(data, fast_period=12, slow_period=26, signal_period=9):
        """
        Calcula o Moving Average Convergence Divergence (MACD)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - fast_period: Período para a EMA rápida
        - slow_period: Período para a EMA lenta
        - signal_period: Período para a linha de sinal
        
        Retorno:
        - macd, signal, histogram: Séries com os valores do MACD
        """
        close_col = 'close' if 'close' in data.columns else data.columns[0]
        series = data[close_col]
        
        # Calcular as exponential moving averages
        ema_fast = series.ewm(span=fast_period, adjust=False).mean()
        ema_slow = series.ewm(span=slow_period, adjust=False).mean()
        
        # Calcular MACD e Signal Line
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # Calcular histograma
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram

    @staticmethod
    def getAtr(data, period=14):
        """
        Calcula o Average True Range (ATR)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do ATR
        
        Retorno:
        - Série com os valores do ATR
        """
        # Verificar se as colunas necessárias existem
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular True Range
        high_low = data['high'] - data['low']
        high_close = abs(data['high'] - data['close'].shift(1))
        low_close = abs(data['low'] - data['close'].shift(1))
        
        # True Range é o maior dos três valores
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Calcular ATR como média móvel do True Range
        atr = tr.rolling(window=period).mean()
        
        return atr

    @staticmethod
    def getBollingerBands(data, period=20, num_std=2.0):
        """
        Calcula as Bandas de Bollinger
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo das médias
        - num_std: Número de desvios padrão para as bandas
        
        Retorno:
        - middle, upper, lower: Séries com os valores das bandas
        """
        close_col = 'close' if 'close' in data.columns else data.columns[0]
        series = data[close_col]
        
        # Calcular a média móvel (banda do meio)
        middle = series.rolling(window=period).mean()
        
        # Calcular o desvio padrão
        std_dev = series.rolling(window=period).std()
        
        # Calcular as bandas superior e inferior
        upper = middle + (std_dev * num_std)
        lower = middle - (std_dev * num_std)
        
        return middle, upper, lower

    @staticmethod
    def getStochasticRSI(data, rsi_period=14, stoch_period=14, k_period=3, d_period=3):
        """
        Calcula o Stochastic RSI
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - rsi_period: Período para cálculo do RSI
        - stoch_period: Período para o estocástico
        - k_period: Período para suavização do %K
        - d_period: Período para suavização do %D
        
        Retorno:
        - k, d: Séries com os valores do Stochastic RSI
        """
        # Calcular RSI
        rsi_values = Indicators.getRSI(data, window=rsi_period, last_only=False)
        
        # Calcular máximos e mínimos do RSI no período
        rsi_min = rsi_values.rolling(window=stoch_period).min()
        rsi_max = rsi_values.rolling(window=stoch_period).max()
        
        # Calcular Stochastic RSI
        # Evitar divisão por zero
        denominator = rsi_max - rsi_min
        denominator = denominator.replace(0, np.finfo(float).eps)
        
        stoch_rsi = (rsi_values - rsi_min) / denominator
        
        # Calcular %K e %D
        k = stoch_rsi.rolling(window=k_period).mean() * 100
        d = k.rolling(window=d_period).mean()
        
        return k, d
    @staticmethod
    def getKDJ(data, k_period=9, d_period=3, j_period=3):
        """
        Calcula o indicador KDJ
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - k_period: Período para cálculo do %K
        - d_period: Período para cálculo do %D
        - j_period: Período para cálculo do %J
        
        Retorno:
        - k, d, j: Séries com os valores do KDJ
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular os mínimos e máximos para o período
        low_min = data['low'].rolling(window=k_period).min()
        high_max = data['high'].rolling(window=k_period).max()
        
        # Calcular RSV (Raw Stochastic Value)
        # Evitar divisão por zero
        denominator = high_max - low_min
        denominator = denominator.replace(0, np.finfo(float).eps)
        
        rsv = (data['close'] - low_min) / denominator * 100
        
        # Calcular K, D, J
        k = rsv.ewm(span=d_period, adjust=False).mean()
        d = k.ewm(span=d_period, adjust=False).mean()
        j = 3 * k - 2 * d
        
        return k, d, j

    @staticmethod
    def getWilliamsR(data, period=14):
        """
        Calcula o Williams %R
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo
        
        Retorno:
        - Série com os valores do Williams %R
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular os máximos e mínimos para o período
        high_max = data['high'].rolling(window=period).max()
        low_min = data['low'].rolling(window=period).min()
        
        # Calcular Williams %R
        # Evitar divisão por zero
        denominator = high_max - low_min
        denominator = denominator.replace(0, np.finfo(float).eps)
        
        williams_r = ((high_max - data['close']) / denominator) * -100
        
        return williams_r

    @staticmethod
    def getIchimoku(data, tenkan_period=9, kijun_period=26, senkou_span_b_period=52, displacement=26):
        """
        Calcula o Ichimoku Cloud
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - tenkan_period: Período para o Tenkan-sen (Linha de Conversão)
        - kijun_period: Período para o Kijun-sen (Linha Base)
        - senkou_span_b_period: Período para o Senkou Span B (Segunda linha da nuvem)
        - displacement: Período de deslocamento para o Senkou Span (Nuvem)
        
        Retorno:
        - tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span: Séries com os componentes do Ichimoku
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Função para calcular a média dos máximos/mínimos de um período
        def donchian(high, low, period):
            return (high.rolling(window=period).max() + low.rolling(window=period).min()) / 2
        
        # Calcular os componentes do Ichimoku
        tenkan_sen = donchian(data['high'], data['low'], tenkan_period)
        kijun_sen = donchian(data['high'], data['low'], kijun_period)
        
        # Senkou Span A (Primeira linha da nuvem)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
        
        # Senkou Span B (Segunda linha da nuvem)
        senkou_span_b = donchian(data['high'], data['low'], senkou_span_b_period).shift(displacement)
        
        # Chikou Span (Linha de Atraso)
        chikou_span = data['close'].shift(-displacement)
        
        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span

    @staticmethod
    def getSupertrend(data, period=14, multiplier=3.0):
        """
        Calcula o indicador Supertrend
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do ATR
        - multiplier: Multiplicador para as bandas
        
        Retorno:
        - supertrend, direction: Séries com os valores do Supertrend e a direção
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular ATR
        atr = Indicators.getAtr(data, period=period)
        
        # Calcular bandas do Supertrend
        hl2 = (data['high'] + data['low']) / 2
        
        # Banda superior básica e banda inferior básica
        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)
        
        # Preparar arrays para os resultados
        supertrend = np.zeros_like(data['close'])
        direction = np.zeros_like(data['close'])  # 1 para tendência de alta, -1 para tendência de baixa
        
        # Calculando o Supertrend
        for i in range(1, len(data)):
            if data['close'].iloc[i] > upperband.iloc[i-1]:
                supertrend[i] = lowerband.iloc[i]
                direction[i] = 1
            elif data['close'].iloc[i] < lowerband.iloc[i-1]:
                supertrend[i] = upperband.iloc[i]
                direction[i] = -1
            else:
                supertrend[i] = supertrend[i-1]
                direction[i] = direction[i-1]
                
                if direction[i] == 1 and lowerband.iloc[i] < supertrend[i]:
                    supertrend[i] = lowerband.iloc[i]
                elif direction[i] == -1 and upperband.iloc[i] > supertrend[i]:
                    supertrend[i] = upperband.iloc[i]
        
        return pd.Series(supertrend, index=data.index), pd.Series(direction, index=data.index)
    @staticmethod
 
    @staticmethod
    def getTrueStrengthIndex(data, r_period=25, s_period=13, signal_period=7, use_close=True):
        """
        Calcula o indicador True Strength Index (TSI)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - r_period: Período para a primeira suavização
        - s_period: Período para a segunda suavização
        - signal_period: Período para a linha de sinal
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - tsi, tsi_signal: Séries com os valores do TSI e sua linha de sinal
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular a mudança de preço
        price_change = data[price_col].diff()
        
        # Primeira suavização da mudança de preço (EMA do período r_period)
        pc_ema_r = price_change.ewm(span=r_period, adjust=False).mean()
        
        # Segunda suavização (EMA do resultado anterior de período s_period)
        pc_ema_r_s = pc_ema_r.ewm(span=s_period, adjust=False).mean()
        
        # Primeira suavização do valor absoluto da mudança de preço
        abs_pc_ema_r = price_change.abs().ewm(span=r_period, adjust=False).mean()
        
        # Segunda suavização do valor absoluto
        abs_pc_ema_r_s = abs_pc_ema_r.ewm(span=s_period, adjust=False).mean()
        
        # Calcular TSI
        # Evitar divisão por zero
        denominator = abs_pc_ema_r_s.replace(0, np.finfo(float).eps)
        tsi = 100 * (pc_ema_r_s / denominator)
        
        # Calcular linha de sinal (EMA do TSI)
        tsi_signal = tsi.ewm(span=signal_period, adjust=False).mean()
        
        return tsi, tsi_signal

    @staticmethod
    def getUltimateOscillator(data, period1=7, period2=14, period3=28, weight1=4.0, weight2=2.0, weight3=1.0):
        """
        Calcula o indicador Ultimate Oscillator
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period1: Primeiro período (curto) para média
        - period2: Segundo período (médio) para média
        - period3: Terceiro período (longo) para média
        - weight1: Peso para o primeiro período
        - weight2: Peso para o segundo período
        - weight3: Peso para o terceiro período
        
        Retorno:
        - ultimate_oscillator: Série com os valores do Ultimate Oscillator
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular True Range (TR) e Buying Pressure (BP)
        data = data.copy()
        data['prev_close'] = data['close'].shift(1)
        
        # True Range = max(high, prev_close) - min(low, prev_close)
        data['tr'] = data.apply(
            lambda x: max(x['high'], x['prev_close']) - min(x['low'], x['prev_close']) 
            if not pd.isna(x['prev_close']) else x['high'] - x['low'],
            axis=1
        )
        
        # Buying Pressure = close - min(low, prev_close)
        data['bp'] = data.apply(
            lambda x: x['close'] - min(x['low'], x['prev_close'])
            if not pd.isna(x['prev_close']) else x['close'] - x['low'],
            axis=1
        )
        
        # Calcular as médias móveis para diferentes períodos
        # Average1 = Sum(BP, period1) / Sum(TR, period1)
        data['avg1'] = data['bp'].rolling(window=period1).sum() / data['tr'].rolling(window=period1).sum()
        
        # Average2 = Sum(BP, period2) / Sum(TR, period2)
        data['avg2'] = data['bp'].rolling(window=period2).sum() / data['tr'].rolling(window=period2).sum()
        
        # Average3 = Sum(BP, period3) / Sum(TR, period3)
        data['avg3'] = data['bp'].rolling(window=period3).sum() / data['tr'].rolling(window=period3).sum()
        
        # Calcular o Ultimate Oscillator
        # UO = 100 * ((weight1 * Average1) + (weight2 * Average2) + (weight3 * Average3)) / (weight1 + weight2 + weight3)
        total_weight = weight1 + weight2 + weight3
        data['uo'] = 100 * ((weight1 * data['avg1'] + 
                             weight2 * data['avg2'] + 
                             weight3 * data['avg3']) / total_weight)
        
        return data['uo']

    @staticmethod
    def getVIDYA(data, period=14, chande_period=10, use_close=True):
        """
        Calcula o indicador VIDYA (Variable Index Dynamic Average)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do indicador
        - chande_period: Período para cálculo do Chande Momentum Oscillator
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - vidya: Série com os valores do VIDYA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular o Chande Momentum Oscillator (CMO)
        price_change = data[price_col].diff(1)
        
        # Separar as variações positivas e negativas
        gain = np.where(price_change > 0, price_change, 0)
        loss = np.where(price_change < 0, -price_change, 0)
        
        # Calcular a soma das variações positivas e negativas para o período
        sum_gain = pd.Series(gain).rolling(window=chande_period).sum()
        sum_loss = pd.Series(loss).rolling(window=chande_period).sum()
        
        # Calcular o CMO
        cmo = 100 * ((sum_gain - sum_loss) / (sum_gain + sum_loss).replace(0, np.finfo(float).eps))
        
        # Calcular o fator de suavização baseado no CMO
        # SC = 2 / (period + 1) é o fator de suavização tradicional do EMA
        sc = 2 / (period + 1)
        
        # O CMO normalizado para o range 0-1
        k = abs(cmo) / 100
        
        # Inicializar VIDYA com o primeiro valor válido de preço
        vidya = np.zeros(len(data))
        vidya[:] = np.nan
        
        # Encontrar o primeiro índice válido (onde CMO não é NaN)
        first_valid = cmo.first_valid_index()
        if first_valid is not None:
            idx = data.index.get_loc(first_valid)
            # Inicializar VIDYA com o primeiro valor de preço
            vidya[idx] = data[price_col].iloc[idx]
            
            # Calcular VIDYA para os valores restantes
            for i in range(idx + 1, len(data)):
                # Fator de suavização ajustado pela volatilidade (k)
                alpha = sc * k.iloc[i]
                # VIDYA(i) = VIDYA(i-1) + α * (Price(i) - VIDYA(i-1))
                vidya[i] = vidya[i-1] + alpha * (data[price_col].iloc[i] - vidya[i-1])
        
        return pd.Series(vidya, index=data.index)
    @staticmethod
    def getVolumeWeightedAveragePrice(data, period=14, reset_daily=True):
        """
        Calcula o indicador Volume-Weighted Average Price (VWAP)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para o cálculo
        - reset_daily: Resetar cálculos diariamente
        
        Retorno:
        - vwap, upper_band, lower_band: Séries com os valores do VWAP e suas bandas
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        data = data.copy()
        
        # Verificar se temos a data para separar dias
        date_column = None
        for col in ['date', 'datetime', 'timestamp']:
            if col in data.columns:
                date_column = col
                break
        
        # Calcular o preço típico (high + low + close) / 3
        data['typical_price'] = (data['high'] + data['low'] + data['close']) / 3
        
        # Calcular o valor negociado (preço típico * volume)
        data['tp_volume'] = data['typical_price'] * data['volume']
        
        if reset_daily and date_column:
            # Extrair apenas a data (sem hora) para agrupar por dia
            if pd.api.types.is_datetime64_any_dtype(data[date_column]):
                data['day'] = data[date_column].dt.date
            else:
                # Tentar converter para datetime
                try:
                    data['day'] = pd.to_datetime(data[date_column]).dt.date
                except:
                    # Se não conseguir converter, usar o dia do index (se for datetime)
                    if pd.api.types.is_datetime64_any_dtype(data.index):
                        data['day'] = data.index.date
                    else:
                        # Se tudo falhar, não resetar diariamente
                        reset_daily = False
        
        # Calcular o VWAP
        if reset_daily and 'day' in data.columns:
            # Resetar os cálculos por dia
            data['cum_tp_volume'] = data.groupby('day')['tp_volume'].cumsum()
            data['cum_volume'] = data.groupby('day')['volume'].cumsum()
        else:
            # Acumular continuamente
            data['cum_tp_volume'] = data['tp_volume'].cumsum()
            data['cum_volume'] = data['volume'].cumsum()
        
        # Evitar divisão por zero
        data['vwap'] = np.where(
            data['cum_volume'] > 0,
            data['cum_tp_volume'] / data['cum_volume'],
            data['typical_price']
        )
        
        # Calcular desvio do preço em relação ao VWAP
        data['price_dev'] = data['typical_price'] - data['vwap']
        
        # Calcular desvio padrão do preço em relação ao VWAP
        if reset_daily and 'day' in data.columns:
            data['std_dev'] = data.groupby('day')['price_dev'].rolling(window=period).std().reset_index(level=0, drop=True)
        else:
            data['std_dev'] = data['price_dev'].rolling(window=period).std()
        
        # Preencher valores NaN
        data['std_dev'] = data['std_dev'].fillna(0)
        
        # Calcular bandas de desvio padrão
        data['upper_band'] = data['vwap'] + (data['std_dev'] * 2)
        data['lower_band'] = data['vwap'] - (data['std_dev'] * 2)
        
        return data['vwap'], data['upper_band'], data['lower_band']
    @staticmethod
    def getWilliamsAlligator(data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3):
        """
        Calcula o indicador Williams Alligator
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - jaw_period: Período para a mandíbula
        - jaw_offset: Deslocamento para a mandíbula
        - teeth_period: Período para os dentes
        - teeth_offset: Deslocamento para os dentes
        - lips_period: Período para os lábios
        - lips_offset: Deslocamento para os lábios
        
        Retorno:
        - jaw, teeth, lips: Séries com os valores dos componentes do Williams Alligator
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o preço médio
        data = data.copy()
        data['median_price'] = (data['high'] + data['low']) / 2
        
        # Função para calcular SMMA (Smoothed Moving Average)
        def calculate_smma(price_series, period):
            smma = np.zeros_like(price_series)
            smma[:period] = np.nan
            
            # Inicializar com a média dos primeiros 'period' elementos
            smma[period - 1] = np.mean(price_series[:period])
            
            # Calcular o SMMA para os elementos restantes
            for i in range(period, len(price_series)):
                smma[i] = (smma[i - 1] * (period - 1) + price_series[i]) / period
            
            return smma
        
        # Calcular as três linhas do Alligator
        jaw_smma = calculate_smma(data['median_price'].values, jaw_period)
        teeth_smma = calculate_smma(data['median_price'].values, teeth_period)
        lips_smma = calculate_smma(data['median_price'].values, lips_period)
        
        # Criar séries
        jaw = pd.Series(jaw_smma, index=data.index)
        teeth = pd.Series(teeth_smma, index=data.index)
        lips = pd.Series(lips_smma, index=data.index)
        
        # Aplicar os deslocamentos (shift)
        jaw_shifted = jaw.shift(-jaw_offset)  # Futuro
        teeth_shifted = teeth.shift(-teeth_offset)  # Futuro
        lips_shifted = lips.shift(-lips_offset)  # Futuro
        
        return jaw_shifted, teeth_shifted, lips_shifted
    
    @staticmethod
    def getWMA(data, period=14, use_close=True):
        """
        Calcula o indicador WMA (Weighted Moving Average)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do WMA
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - wma: Série com os valores do WMA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Gerar pesos para o WMA
        weights = np.arange(1, period + 1)
        
        # Calcular o WMA
        wma = data[price_col].rolling(window=period).apply(
            lambda x: np.sum(weights * x) / np.sum(weights), raw=True
        )
        
        return wma
    
    @staticmethod
    def getZeroLagMovingAverage(data, period=14, use_close=True):
        """
        Calcula o indicador Zero-Lag Moving Average (ZLEMA)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do ZLEMA
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - zlema: Série com os valores do ZLEMA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular lag (compensação para remover o atraso)
        lag = (period - 1) // 2
        
        # Calcular o ZLEMA (EMA com duplos preços menos o preço atrasado)
        zlema_input = 2 * data[price_col] - data[price_col].shift(lag)
        zlema = zlema_input.ewm(span=period, adjust=False).mean()
        
        return zlema
    @staticmethod
    def getOBV(data):
        """
        Calcula o indicador OBV (On Balance Volume)
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        
        Retorno:
        - obv: Série com os valores do On Balance Volume
        """
        # Verificar se temos os dados necessários
        required_cols = ['close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular OBV
        data = data.copy()
        data['price_change'] = data['close'].diff()
        data['obv'] = 0
        
        # Inicialização do OBV
        data.loc[1:, 'obv'] = np.nan
        
        # Para o primeiro dia, OBV é igual ao volume
        if len(data) > 0:
            data.loc[0, 'obv'] = data.loc[0, 'volume']
        
        # Cálculo do OBV para os dias seguintes
        for i in range(1, len(data)):
            if data.loc[i, 'price_change'] > 0:
                data.loc[i, 'obv'] = data.loc[i-1, 'obv'] + data.loc[i, 'volume']
            elif data.loc[i, 'price_change'] < 0:
                data.loc[i, 'obv'] = data.loc[i-1, 'obv'] - data.loc[i, 'volume']
            else:
                data.loc[i, 'obv'] = data.loc[i-1, 'obv']
        
        return data['obv']
    @staticmethod
    def getAcceleratorOscillator(data, sma_period=5, ao_period_fast=5, ao_period_slow=34):
        """
        Calcula o indicador Accelerator Oscillator (AC)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - sma_period: Período para cálculo da média móvel simples do AO
        - ao_period_fast: Período rápido para o Awesome Oscillator
        - ao_period_slow: Período lento para o Awesome Oscillator
        
        Retorno:
        - accelerator_oscillator: Série com os valores do Accelerator Oscillator
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o preço médio (median price)
        data = data.copy()
        data['median_price'] = (data['high'] + data['low']) / 2
        
        # Calcular o Awesome Oscillator (AO)
        # 1. SMA do preço médio para período rápido
        data['ao_fast'] = data['median_price'].rolling(window=ao_period_fast).mean()
        
        # 2. SMA do preço médio para período lento
        data['ao_slow'] = data['median_price'].rolling(window=ao_period_slow).mean()
        
        # 3. Awesome Oscillator = SMA Rápido - SMA Lento
        data['awesome_oscillator'] = data['ao_fast'] - data['ao_slow']
        
        # Calcular o Accelerator Oscillator (AC)
        # AC = AO - SMA(AO, sma_period)
        data['ao_sma'] = data['awesome_oscillator'].rolling(window=sma_period).mean()
        data['accelerator_oscillator'] = data['awesome_oscillator'] - data['ao_sma']
        
        return data['accelerator_oscillator']
    @staticmethod
    def getALMA(data, period=14, sigma=6.0, offset=0.85, use_close=True):
        """
        Calcula o indicador ALMA (Arnaud Legoux Moving Average)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do ALMA
        - sigma: Controla a suavidade da curva (padrão=6)
        - offset: Controla a reatividade vs lag (0=mais lag, 1=mais reatividade)
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - alma: Série com os valores do ALMA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular os parâmetros para o ALMA
        m = np.floor(offset * (period - 1))
        s = period / sigma
        
        # Calcular os pesos do ALMA
        weights = np.zeros(period)
        for i in range(period):
            weights[i] = np.exp(-((i - m) ** 2) / (2 * s * s))
        
        # Normalizar os pesos
        weights = weights / np.sum(weights)
        
        # Aplicar os pesos à janela móvel
        alma = data[price_col].rolling(window=period).apply(
            lambda x: np.sum(weights * x), raw=True
        )
        
        return alma
    
    @staticmethod
    def getAroon(data, period=14):
        """
        Calcula o indicador Aroon
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do Aroon
        
        Retorno:
        - aroon_up, aroon_down, aroon_oscillator: Séries com os valores do Aroon
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular os índices do máximo e mínimo no período
        high_idx = data['high'].rolling(window=period).apply(
            lambda x: period - x.argmax() - 1 if not np.isnan(x).all() else np.nan
        )
        
        low_idx = data['low'].rolling(window=period).apply(
            lambda x: period - x.argmin() - 1 if not np.isnan(x).all() else np.nan
        )
        
        # Calcular Aroon Up e Aroon Down
        aroon_up = 100 * (period - high_idx) / period
        aroon_down = 100 * (period - low_idx) / period
        
        # Calcular Aroon Oscillator
        aroon_oscillator = aroon_up - aroon_down
        
        return aroon_up, aroon_down, aroon_oscillator

    @staticmethod
    def getAroonOscillator(data, period=14):
        """
        Calcula o indicador Aroon Oscillator
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do Aroon Oscillator
        
        Retorno:
        - aroon_oscillator: Série com os valores do Aroon Oscillator
        """
        aroon_up, aroon_down, aroon_oscillator = Indicators.getAroon(data, period)
        return aroon_oscillator
    
    @staticmethod
    def getAwesomeOscillator(data, fast_period=5, slow_period=34):
        """
        Calcula o indicador Awesome Oscillator
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - fast_period: Período para a média móvel rápida
        - slow_period: Período para a média móvel lenta
        
        Retorno:
        - awesome_oscillator: Série com os valores do Awesome Oscillator
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o preço médio (median price)
        data = data.copy()
        data['median_price'] = (data['high'] + data['low']) / 2
        
        # Calcular o Awesome Oscillator (AO)
        # 1. SMA do preço médio para período rápido
        data['ao_fast'] = data['median_price'].rolling(window=fast_period).mean()
        
        # 2. SMA do preço médio para período lento
        data['ao_slow'] = data['median_price'].rolling(window=slow_period).mean()
        
        # 3. Awesome Oscillator = SMA Rápido - SMA Lento
        data['awesome_oscillator'] = data['ao_fast'] - data['ao_slow']
        
        return data['awesome_oscillator']

    @staticmethod
    def getChandeMomentumOscillator(data, period=14, use_close=True):
        """
        Calcula o indicador Chande Momentum Oscillator (CMO)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do CMO
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - cmo: Série com os valores do Chande Momentum Oscillator
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular variação diária
        price_change = data[price_col].diff()
        
        # Separar as variações positivas e negativas
        gain = np.where(price_change > 0, price_change, 0)
        loss = np.where(price_change < 0, -price_change, 0)
        
        # Converter para Series
        gain_series = pd.Series(gain, index=data.index)
        loss_series = pd.Series(loss, index=data.index)
        
        # Calcular a soma das variações positivas e negativas para o período
        sum_gains = gain_series.rolling(window=period).sum()
        sum_losses = loss_series.rolling(window=period).sum()
        
        # Calcular o CMO
        # CMO = 100 * ((sum_gains - sum_losses) / (sum_gains + sum_losses))
        denominator = sum_gains + sum_losses
        denominator = denominator.replace(0, np.finfo(float).eps)  # Evitar divisão por zero
        
        cmo = 100 * ((sum_gains - sum_losses) / denominator)
        
        return cmo

    @staticmethod
    def getChaikinOscillator(data, fast_period=3, slow_period=10):
        """
        Calcula o indicador Chaikin Oscillator
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        - fast_period: Período para a EMA rápida
        - slow_period: Período para a EMA lenta
        
        Retorno:
        - chaikin_oscillator: Série com os valores do Chaikin Oscillator
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o Money Flow Multiplier
        data = data.copy()
        data['mf_multiplier'] = ((data['close'] - data['low']) - (data['high'] - data['close'])) / (data['high'] - data['low'])
        
        # Lidar com casos onde high == low (evitar divisão por zero)
        data['mf_multiplier'] = data['mf_multiplier'].replace([np.inf, -np.inf], 0)
        data['mf_multiplier'] = data['mf_multiplier'].fillna(0)
        
        # Calcular o Money Flow Volume
        data['mf_volume'] = data['mf_multiplier'] * data['volume']
        
        # Calcular a Accumulation/Distribution Line (ADL)
        data['adl'] = data['mf_volume'].cumsum()
        
        # Calcular EMA rápida e lenta da ADL
        data['adl_ema_fast'] = data['adl'].ewm(span=fast_period, adjust=False).mean()
        data['adl_ema_slow'] = data['adl'].ewm(span=slow_period, adjust=False).mean()
        
        # Calcular o Chaikin Oscillator
        data['chaikin_osc'] = data['adl_ema_fast'] - data['adl_ema_slow']
        
        return data['chaikin_osc']
    @staticmethod
    def getCMF(data, period=20):
        """
        Calcula o indicador CMF (Chaikin Money Flow)
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        - period: Período para cálculo do CMF
        
        Retorno:
        - cmf: Série com os valores do Chaikin Money Flow
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o Money Flow Multiplier
        data = data.copy()
        data['mf_multiplier'] = ((data['close'] - data['low']) - (data['high'] - data['close'])) / (data['high'] - data['low'])
        
        # Lidar com casos onde high == low (evitar divisão por zero)
        data['mf_multiplier'] = data['mf_multiplier'].replace([np.inf, -np.inf], 0)
        data['mf_multiplier'] = data['mf_multiplier'].fillna(0)
        
        # Calcular o Money Flow Volume
        data['mf_volume'] = data['mf_multiplier'] * data['volume']
        
        # Calcular o Chaikin Money Flow
        # CMF = Sum(Money Flow Volume, period) / Sum(Volume, period)
        cmf = data['mf_volume'].rolling(window=period).sum() / data['volume'].rolling(window=period).sum()
        
        return cmf
    @staticmethod
    def getDetrendedPriceOscillator(data, period=14, sma_period=15):
        """
        Calcula o indicador Detrended Price Oscillator (DPO)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do DPO
        - sma_period: Período para cálculo da SMA
        
        Retorno:
        - dpo: Série com os valores do Detrended Price Oscillator
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do Detrended Price Oscillator")
        
        # Calcular o deslocamento
        shift_period = int(period / 2 + 1)
        
        # Calcular a média móvel simples (SMA)
        sma = data['close'].rolling(window=sma_period).mean()
        
        # Calcular o DPO
        # DPO = Close(i) - SMA(i - (period/2 + 1))
        dpo = data['close'] - sma.shift(shift_period)
        
        return dpo
    @staticmethod
    def getDonchianChannel(data, period=20):
        """
        Calcula o indicador Donchian Channel
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo das bandas
        
        Retorno:
        - upper_band, middle_band, lower_band: Séries com os valores das bandas
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular as bandas do Donchian Channel
        upper_band = data['high'].rolling(window=period).max()
        lower_band = data['low'].rolling(window=period).min()
        middle_band = (upper_band + lower_band) / 2
        
        return upper_band, middle_band, lower_band

    @staticmethod
    def getDonchianChannels(data, period=20):
        """
        Calcula o indicador Donchian Channels (alias para getDonchianChannel)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo das bandas
        
        Retorno:
        - upper_band, middle_band, lower_band: Séries com os valores das bandas
        """
        return Indicators.getDonchianChannel(data, period)
    @staticmethod
    def getEhlerFisherTransform(data, period=10):
        """
        Calcula o indicador Ehler Fisher Transform
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do EFT
        
        Retorno:
        - fisher_transform: Série com os valores do Ehler Fisher Transform
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o valor médio (midpoint) do período
        data = data.copy()
        data['price_mid'] = (data['high'] + data['low']) / 2
        
        # Iniciar valores
        data['max_h'] = np.nan
        data['min_l'] = np.nan
        
        # Preencher a primeira linha com valores iniciais para evitar NaN
        if len(data) > 0:
            data.loc[0, 'max_h'] = data.loc[0, 'price_mid']
            data.loc[0, 'min_l'] = data.loc[0, 'price_mid']
        
        # Calcular máximos e mínimos com um método adaptativo (Ehlers)
        # Isso usa uma técnica de alisamento que é mais responsiva a mudanças recentes
        alpha = 2.0 / (period + 1.0)
        
        for i in range(1, len(data)):
            # Atualizar máximo
            max_value = data.loc[i-1, 'max_h']
            if data.loc[i, 'price_mid'] > max_value:
                max_value = data.loc[i, 'price_mid']
            else:
                max_value = max_value - alpha * (max_value - data.loc[i, 'price_mid'])
            data.loc[i, 'max_h'] = max_value
            
            # Atualizar mínimo
            min_value = data.loc[i-1, 'min_l']
            if data.loc[i, 'price_mid'] < min_value:
                min_value = data.loc[i, 'price_mid']
            else:
                min_value = min_value + alpha * (data.loc[i, 'price_mid'] - min_value)
            data.loc[i, 'min_l'] = min_value
        
        # Normalizar os preços para o intervalo [-1, 1]
        data['value'] = np.nan
        
        # Calcular o valor normalizado
        for i in range(1, len(data)):
            price_range = data.loc[i, 'max_h'] - data.loc[i, 'min_l']
            if price_range == 0:
                data.loc[i, 'value'] = 0
            else:
                # Fórmula de Ehlers para normalização
                data.loc[i, 'value'] = 2 * ((data.loc[i, 'price_mid'] - data.loc[i, 'min_l']) / price_range - 0.5)
        
        # Suavizar o valor normalizado com uma média móvel
        data['smooth_value'] = data['value'].rolling(window=period).mean().fillna(0)
        
        # Limitar o valor a +/- 0.999 para evitar infinitos na transformação
        data['smooth_value'] = np.clip(data['smooth_value'], -0.999, 0.999)
        
        # Aplicar a transformação de Fisher
        data['fisher'] = 0.5 * np.log((1 + data['smooth_value']) / (1 - data['smooth_value']))
        
        return data['fisher']
    @staticmethod
    def getElderForceIndex(data, period=13):
        """
        Calcula o indicador Elder Force Index
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        - period: Período para cálculo da média móvel do Force Index
        
        Retorno:
        - force_index: Série com os valores do Elder Force Index
        """
        # Verificar se temos os dados necessários
        required_cols = ['close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular a variação do preço
        data = data.copy()
        data['price_change'] = data['close'].diff(1)
        
        # Calcular o Force Index bruto
        data['force_index_raw'] = data['price_change'] * data['volume']
        
        # Calcular o Force Index suavizado com EMA
        force_index = data['force_index_raw'].ewm(span=period, adjust=False).mean()
        
        return force_index

    @staticmethod
    def getElderRay(data, period=13):
        """
        Calcula o indicador Elder Ray
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo da média móvel
        
        Retorno:
        - bull_power, bear_power: Séries com os valores do Bull Power e Bear Power
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular a média móvel
        data = data.copy()
        data['ma'] = data['close'].ewm(span=period, adjust=False).mean()
        
        # Calcular o Bull Power e Bear Power
        bull_power = data['high'] - data['ma']
        bear_power = data['low'] - data['ma']
        
        return bull_power, bear_power
    
    @staticmethod
    def getFisherTransform(data, period=10):
        """
        Calcula o indicador Fisher Transform
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do Fisher Transform
        
        Retorno:
        - fisher_transform: Série com os valores do Fisher Transform
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o valor médio (midpoint) do período
        data = data.copy()
        data['price_mid'] = (data['high'] + data['low']) / 2
        
        # Encontrar o máximo e mínimo para o período
        data['period_high'] = data['price_mid'].rolling(window=period).max()
        data['period_low'] = data['price_mid'].rolling(window=period).min()
        
        # Normalizar os preços para o intervalo [-1, 1]
        data['value'] = np.nan
        
        # Evitar divisão por zero
        data['price_range'] = data['period_high'] - data['period_low']
        data['price_range'] = data['price_range'].replace(0, np.finfo(float).eps)
        
        data['value'] = 2 * ((data['price_mid'] - data['period_low']) / data['price_range'] - 0.5)
        
        # Calcular o Fisher Transform
        data['fisher_input'] = data['value'].rolling(window=period).mean()
        
        # Limitar o valor a +/- 0.999 para evitar infinitos na transformação
        data['fisher_input'] = np.clip(data['fisher_input'], -0.999, 0.999)
        
        # Aplicar a transformação de Fisher
        data['fisher'] = 0.5 * np.log((1 + data['fisher_input']) / (1 - data['fisher_input']))
        
        return data['fisher']

    @staticmethod
    def getForceIndex(data, period=13):
        """
        Calcula o indicador Force Index
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        - period: Período para cálculo da média móvel do Force Index
        
        Retorno:
        - force_index: Série com os valores do Force Index
        """
        # Este é apenas um alias para getElderForceIndex
        return Indicators.getElderForceIndex(data, period)
    
    @staticmethod
    def getFractals(data, window=2):
        """
        Calcula o indicador Fractals de Bill Williams
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - window: Tamanho da janela para cada lado do centro (total de 2*window+1 barras)
        
        Retorno:
        - fractal_up, fractal_down: Séries com os valores dos fractais de alta e baixa
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Inicializar os arrays de resultado
        data = data.copy()
        data['fractal_up'] = False
        data['fractal_down'] = False
        
        # Um fractal de alta ocorre quando o high atual é maior que n high anteriores e posteriores
        # Um fractal de baixa ocorre quando o low atual é menor que n low anteriores e posteriores
        
        for i in range(window, len(data) - window):
            # Verificar fractal de alta
            if all(data['high'].iloc[i] > data['high'].iloc[i-j] for j in range(1, window+1)) and \
               all(data['high'].iloc[i] > data['high'].iloc[i+j] for j in range(1, window+1)):
                data.iloc[i, data.columns.get_loc('fractal_up')] = True
            
            # Verificar fractal de baixa
            if all(data['low'].iloc[i] < data['low'].iloc[i-j] for j in range(1, window+1)) and \
               all(data['low'].iloc[i] < data['low'].iloc[i+j] for j in range(1, window+1)):
                data.iloc[i, data.columns.get_loc('fractal_down')] = True
        
        return data['fractal_up'], data['fractal_down']
    
    @staticmethod
    def getGatorOscillator(data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3):
        """
        Calcula o indicador Gator Oscillator
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - jaw_period: Período para a mandíbula
        - jaw_offset: Deslocamento para a mandíbula
        - teeth_period: Período para os dentes
        - teeth_offset: Deslocamento para os dentes
        - lips_period: Período para os lábios
        - lips_offset: Deslocamento para os lábios
        
        Retorno:
        - jaw_teeth, teeth_lips: Séries com os valores do Gator Oscillator
        """
        # Primeiro obtemos as linhas do Alligator
        jaw, teeth, lips = Indicators.getWilliamsAlligator(
            data, jaw_period, jaw_offset, teeth_period, teeth_offset, lips_period, lips_offset
        )
        
        # Calcular o Gator Oscillator
        # Parte superior - distância entre Jaw e Teeth (valor absoluto)
        jaw_teeth = np.abs(jaw - teeth)
        
        # Parte inferior - distância entre Teeth e Lips (valor absoluto negativo)
        teeth_lips = -np.abs(teeth - lips)
        
        return jaw_teeth, teeth_lips
    
    @staticmethod
    def getHilbertTransform(data, period=14):
        """
        Calcula uma versão simplificada do indicador Hilbert Transform
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo
        
        Retorno:
        - ht_sine, ht_leadsine, ht_trend: Séries com os componentes do Hilbert Transform
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do Hilbert Transform")
        
        # Este é uma implementação simplificada já que o Hilbert Transform real
        # é bastante complexo e geralmente implementado em bibliotecas como TA-Lib
        
        data = data.copy()
        
        # 1. Média dos preços (aproximação da tendência)
        ht_trend = data['close'].rolling(window=period).mean()
        
        # 2. Componente oscilatório (aproximação do sine wave)
        # Usar transformações básicas para simular o comportamento do Hilbert Transform
        xrad = np.arange(len(data)) * (2 * np.pi / period)
        ht_sine = pd.Series(np.sin(xrad), index=data.index)
        ht_leadsine = pd.Series(np.cos(xrad), index=data.index)
        
        return ht_sine, ht_leadsine, ht_trend

    @staticmethod
    def getHullMovingAverage(data, period=14, use_close=True):
        """
        Calcula o indicador Hull Moving Average (HMA)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do HMA
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - hma: Série com os valores do Hull Moving Average
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular as WMAs para o HMA
        half_period = period // 2
        sqrt_period = int(np.sqrt(period))
        
        # Calcular o WMA com período normal
        wma_period = Indicators.getWMA(data, period, use_close)
        
        # Calcular o WMA com metade do período
        wma_half_period = Indicators.getWMA(data, half_period, use_close)
        
        # Calcular a diferença ponderada
        diff = 2 * wma_half_period - wma_period
        
        # Criar um DataFrame temporário para calcular o WMA final
        temp_df = pd.DataFrame({price_col: diff})
        
        # Calcular o HMA (WMA da diferença ponderada)
        hma = Indicators.getWMA(temp_df, sqrt_period)
        
        return hma

    @staticmethod
    def getKeltnerChannel(data, period=14, atr_period=10, multiplier=2.0, use_ema=True):
        """
        Calcula o indicador Keltner Channel
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo da média móvel central
        - atr_period: Período para cálculo do ATR
        - multiplier: Multiplicador para as bandas
        - use_ema: Usar EMA (True) ou SMA (False) para a linha média
        
        Retorno:
        - middle_line, upper_band, lower_band: Séries com os valores das bandas
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular a média móvel para a linha central
        if use_ema:
            middle_line = data['close'].ewm(span=period, adjust=False).mean()
        else:
            middle_line = data['close'].rolling(window=period).mean()
        
        # Calcular o ATR
        atr = Indicators.getAtr(data, atr_period)
        
        # Calcular as bandas superior e inferior
        upper_band = middle_line + (multiplier * atr)
        lower_band = middle_line - (multiplier * atr)
        
        return middle_line, upper_band, lower_band

    @staticmethod
    def getKeltnerChannels(data, period=14, atr_period=10, multiplier=2.0, use_ema=True):
        """
        Alias para getKeltnerChannel
        """
        return Indicators.getKeltnerChannel(data, period, atr_period, multiplier, use_ema)
    @staticmethod
    def getLinearRegression(data, period=14, use_close=True):
        """
        Calcula o indicador Linear Regression
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo da regressão
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - linear_reg: Série com os valores da regressão linear
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Inicializar a série de resultado
        linear_reg = pd.Series(index=data.index)
        
        # Para cada ponto, calcular a regressão linear para os 'period' pontos anteriores
        for i in range(period, len(data) + 1):
            # Dados para a regressão
            y = data[price_col].iloc[i-period:i].values
            x = np.arange(period)
            
            # Calcular a regressão linear
            slope, intercept = np.polyfit(x, y, 1)
            
            # Valor da regressão no último ponto
            regression_value = intercept + slope * (period - 1)
            
            # Armazenar o valor
            if i < len(data):
                linear_reg.iloc[i-1] = regression_value
        
        return linear_reg
    @staticmethod
    def getMarketFacilitationIndex(data):
        """
        Calcula o indicador Market Facilitation Index (MFI)
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        
        Retorno:
        - mfi: Série com os valores do Market Facilitation Index
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o MFI
        # MFI = (High - Low) / Volume
        mfi = (data['high'] - data['low']) / data['volume'].replace(0, np.finfo(float).eps)
        
        return mfi
    @staticmethod
    def getKAMA(data, period=14, fast_ema=2, slow_ema=30):
        """
        Calcula o indicador KAMA (Kaufman's Adaptive Moving Average)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do Efficiency Ratio
        - fast_ema: Período para EMA rápida
        - slow_ema: Período para EMA lenta
        
        Retorno:
        - kama: Série com os valores do KAMA
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do KAMA")
        
        close = data['close']
        
        # Calcular a mudança de preço direta
        price_change = close.diff(1)
        
        # Calcular o "Efficiency Ratio" (ER)
        direction = abs(close - close.shift(period))
        volatility = abs(price_change).rolling(window=period).sum()
        
        # Evitar divisão por zero
        volatility = volatility.replace(0, np.finfo(float).eps)
        
        er = direction / volatility
        
        # Calcular as constantes suavizadas
        fast_sc = 2.0 / (fast_ema + 1.0)
        slow_sc = 2.0 / (slow_ema + 1.0)
        
        # Calcular o fator de suavização
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        
        # Inicializar o KAMA
        kama = pd.Series(index=close.index)
        
        # Definir o primeiro valor KAMA com o primeiro preço válido
        first_valid_idx = period
        if first_valid_idx < len(close):
            kama.iloc[first_valid_idx] = close.iloc[first_valid_idx]
        
        # Calcular o KAMA para os pontos restantes
        for i in range(first_valid_idx + 1, len(close)):
            kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (close.iloc[i] - kama.iloc[i-1])
        
        return kama
    @staticmethod
    def getMFI(data, period=14):
        """
        Calcula o indicador MFI (Money Flow Index)
        
        Parâmetros:
        - data: DataFrame com os dados de preço e volume
        - period: Período para cálculo do MFI
        
        Retorno:
        - mfi: Série com os valores do Money Flow Index
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular o preço típico
        data = data.copy()
        data['typical_price'] = (data['high'] + data['low'] + data['close']) / 3
        
        # Calcular o fluxo de dinheiro (money flow)
        data['money_flow'] = data['typical_price'] * data['volume']
        
        # Calcular a mudança do preço típico
        data['price_change'] = data['typical_price'].diff()
        
        # Separar fluxo de dinheiro positivo e negativo
        data['positive_flow'] = np.where(data['price_change'] > 0, data['money_flow'], 0)
        data['negative_flow'] = np.where(data['price_change'] < 0, data['money_flow'], 0)
        
        # Calcular a soma dos fluxos positivos e negativos para o período
        data['positive_flow_sum'] = data['positive_flow'].rolling(window=period).sum()
        data['negative_flow_sum'] = data['negative_flow'].rolling(window=period).sum()
        
        # Calcular o Money Ratio
        # Evitar divisão por zero
        data['negative_flow_sum'] = data['negative_flow_sum'].replace(0, np.finfo(float).eps)
        data['money_ratio'] = data['positive_flow_sum'] / data['negative_flow_sum']
        
        # Calcular o MFI
        data['mfi'] = 100 - (100 / (1 + data['money_ratio']))
        
        return data['mfi']
    @staticmethod
    def getMovingAverageEnvelope(data, period=14, envelope_percentage=2.5, use_ema=False):
        """
        Calcula o indicador Moving Average Envelope
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo da média móvel
        - envelope_percentage: Percentual para as bandas
        - use_ema: Usar EMA (True) ou SMA (False)
        
        Retorno:
        - middle, upper, lower: Séries com os valores do Moving Average Envelope
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do Moving Average Envelope")
        
        # Calcular a média móvel
        if use_ema:
            middle = data['close'].ewm(span=period, adjust=False).mean()
        else:
            middle = data['close'].rolling(window=period).mean()
        
        # Calcular o fator do envelope
        envelope_factor = envelope_percentage / 100.0
        
        # Calcular as bandas superior e inferior
        upper = middle * (1 + envelope_factor)
        lower = middle * (1 - envelope_factor)
        
        return middle, upper, lower
    @staticmethod
    def getPivotPoints(data, pivot_type='standard'):
        """
        Calcula o indicador Pivot Points
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - pivot_type: Tipo de cálculo ('standard', 'fibonacci', 'woodie', 'camarilla', 'demark')
        
        Retorno:
        - pivot, s1, s2, s3, r1, r2, r3: Séries com os valores dos níveis de pivot
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Adicionar a coluna open se necessário (para alguns métodos)
        if 'open' not in data.columns and pivot_type.lower() == 'demark':
            data = data.copy()
            data['open'] = data['close'].shift(1)
        
        # Criar DataFrames para os valores anteriores
        data = data.copy()
        data['prev_high'] = data['high'].shift(1)
        data['prev_low'] = data['low'].shift(1)
        data['prev_close'] = data['close'].shift(1)
        if 'open' in data.columns:
            data['prev_open'] = data['open'].shift(1)
        
        # Inicializar séries para os níveis de pivot
        pivot = pd.Series(index=data.index)
        s1 = pd.Series(index=data.index)
        s2 = pd.Series(index=data.index)
        s3 = pd.Series(index=data.index)
        r1 = pd.Series(index=data.index)
        r2 = pd.Series(index=data.index)
        r3 = pd.Series(index=data.index)
        
        # Calcular os Pivot Points de acordo com o método selecionado
        if pivot_type.lower() == 'standard':
            # Pivot Point (PP) = (High + Low + Close) / 3
            pivot = (data['prev_high'] + data['prev_low'] + data['prev_close']) / 3
            
            # Primeira resistência e suporte
            r1 = 2 * pivot - data['prev_low']
            s1 = 2 * pivot - data['prev_high']
            
            # Segunda resistência e suporte
            r2 = pivot + (data['prev_high'] - data['prev_low'])
            s2 = pivot - (data['prev_high'] - data['prev_low'])
            
            # Terceira resistência e suporte
            r3 = r1 + (data['prev_high'] - data['prev_low'])
            s3 = s1 - (data['prev_high'] - data['prev_low'])
        
        elif pivot_type.lower() == 'fibonacci':
            pivot = (data['prev_high'] + data['prev_low'] + data['prev_close']) / 3
            
            range_hl = data['prev_high'] - data['prev_low']
            
            # Resistências (usando níveis de Fibonacci)
            r1 = pivot + 0.382 * range_hl
            r2 = pivot + 0.618 * range_hl
            r3 = pivot + 1.000 * range_hl
            
            # Suportes (usando níveis de Fibonacci)
            s1 = pivot - 0.382 * range_hl
            s2 = pivot - 0.618 * range_hl
            s3 = pivot - 1.000 * range_hl
        
        elif pivot_type.lower() == 'woodie':
            # Woodie dá mais peso ao preço de fechamento
            pivot = (data['prev_high'] + data['prev_low'] + 2 * data['prev_close']) / 4
            
            # Resistências e suportes
            r1 = 2 * pivot - data['prev_low']
            s1 = 2 * pivot - data['prev_high']
            
            r2 = pivot + (data['prev_high'] - data['prev_low'])
            s2 = pivot - (data['prev_high'] - data['prev_low'])
            
            r3 = pivot + 2 * (data['prev_high'] - data['prev_low'])
            s3 = pivot - 2 * (data['prev_high'] - data['prev_low'])
        
        elif pivot_type.lower() == 'camarilla':
            pivot = (data['prev_high'] + data['prev_low'] + data['prev_close']) / 3
            
            range_hl = data['prev_high'] - data['prev_low']
            
            # Resistências (usando multiplicadores específicos)
            r1 = data['prev_close'] + range_hl * 1.1 / 12
            r2 = data['prev_close'] + range_hl * 1.1 / 6
            r3 = data['prev_close'] + range_hl * 1.1 / 4
            
            # Suportes (usando multiplicadores específicos)
            s1 = data['prev_close'] - range_hl * 1.1 / 12
            s2 = data['prev_close'] - range_hl * 1.1 / 6
            s3 = data['prev_close'] - range_hl * 1.1 / 4
        
        elif pivot_type.lower() == 'demark':
            # Condições para determinar o valor X
            x = pd.Series(index=data.index)
            
            # X depende da relação entre close e open
            for i in range(len(data)):
                if data['prev_close'].iloc[i] > data['prev_open'].iloc[i]:
                    x.iloc[i] = data['prev_high'].iloc[i] * 2 + data['prev_low'].iloc[i] + data['prev_close'].iloc[i]
                elif data['prev_close'].iloc[i] < data['prev_open'].iloc[i]:
                    x.iloc[i] = data['prev_high'].iloc[i] + data['prev_low'].iloc[i] * 2 + data['prev_close'].iloc[i]
                else:
                    x.iloc[i] = data['prev_high'].iloc[i] + data['prev_low'].iloc[i] + data['prev_close'].iloc[i] * 2
            
            # Pivot Point DeMark
            pivot = x / 4
            
            # Resistência e suporte
            r1 = x / 2 - data['prev_low']
            s1 = x / 2 - data['prev_high']
            
            # R2, R3, S2, S3 não são definidos no método DeMark original
            r2 = pd.Series(np.nan, index=data.index)
            r3 = pd.Series(np.nan, index=data.index)
            s2 = pd.Series(np.nan, index=data.index)
            s3 = pd.Series(np.nan, index=data.index)
        
        else:
            raise ValueError(f"Tipo de Pivot Point '{pivot_type}' não reconhecido.")
        
        return pivot, s1, s2, s3, r1, r2, r3
    
    @staticmethod
    def getPPO(data, fast_period=12, slow_period=26, signal_period=9):
        """
        Calcula o indicador PPO (Percentage Price Oscillator)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - fast_period: Período para a EMA rápida
        - slow_period: Período para a EMA lenta
        - signal_period: Período para a linha de sinal
        
        Retorno:
        - ppo, ppo_signal, ppo_histogram: Séries com os valores do PPO
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do PPO")
        
        # Calcular EMAs rápida e lenta
        ema_fast = data['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = data['close'].ewm(span=slow_period, adjust=False).mean()
        
        # Calcular o PPO
        # PPO = ((EMA_Rápida - EMA_Lenta) / EMA_Lenta) * 100
        ppo = ((ema_fast - ema_slow) / ema_slow) * 100
        
        # Calcular a linha de sinal (EMA do PPO)
        ppo_signal = ppo.ewm(span=signal_period, adjust=False).mean()
        
        # Calcular o histograma (PPO - Signal)
        ppo_histogram = ppo - ppo_signal
        
        return ppo, ppo_signal, ppo_histogram
    @staticmethod
    def getPriceChannels(data, period=20):
        """
        Calcula o indicador Price Channels
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo dos canais
        
        Retorno:
        - upper, lower: Séries com os valores dos canais de preço
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Calcular os canais de preço
        upper = data['high'].rolling(window=period).max()
        lower = data['low'].rolling(window=period).min()
        
        return upper, lower

    @staticmethod
    def getPSAR(data, af_start=0.02, af_increment=0.02, af_max=0.2):
        """
        Calcula o indicador PSAR (Parabolic Stop and Reverse)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - af_start: Fator de aceleração inicial
        - af_increment: Incremento do fator de aceleração
        - af_max: Fator de aceleração máximo
        
        Retorno:
        - psar: Série com os valores do Parabolic SAR
        """
        # Verificar se temos os dados necessários
        required_cols = ['high', 'low', 'close']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Coluna '{col}' não encontrada nos dados")
        
        # Inicializar colunas
        data = data.copy()
        data['psar'] = np.nan
        data['trend'] = np.nan  # 1 para tendência de alta, -1 para tendência de baixa
        data['af'] = af_start  # Fator de aceleração
        data['ep'] = np.nan  # Extreme point
        
        # Determinar tendência inicial
        # Vamos usar a inclinação dos primeiros preços para determinar a tendência inicial
        if len(data) > 1:
            if data['close'].iloc[1] > data['close'].iloc[0]:
                initial_trend = 1  # Tendência de alta
                data.loc[1, 'psar'] = data['low'].iloc[0]  # PSAR inicial abaixo do primeiro low
                data.loc[1, 'ep'] = data['high'].iloc[1]  # Primeiro EP é o high atual
            else:
                initial_trend = -1  # Tendência de baixa
                data.loc[1, 'psar'] = data['high'].iloc[0]  # PSAR inicial acima do primeiro high
                data.loc[1, 'ep'] = data['low'].iloc[1]  # Primeiro EP é o low atual
            
            data.loc[1, 'trend'] = initial_trend
        
        # Calcular o PSAR para o restante dos dados
        for i in range(2, len(data)):
            prev_psar = data.loc[data.index[i-1], 'psar']
            prev_trend = data.loc[data.index[i-1], 'trend']
            prev_af = data.loc[data.index[i-1], 'af']
            prev_ep = data.loc[data.index[i-1], 'ep']
            
            # Calcular o novo PSAR
            current_psar = prev_psar + prev_af * (prev_ep - prev_psar)
            
            # Tendência de alta
            if prev_trend == 1:
                # Limitar o PSAR pelos mínimos anteriores
                current_psar = min(current_psar, data['low'].iloc[i-2], data['low'].iloc[i-1])
                
                # Verificar se o PSAR é ultrapassado (tendência invertida)
                if current_psar > data['low'].iloc[i]:
                    current_trend = -1
                    current_psar = max(data['high'].iloc[i-2], data['high'].iloc[i-1], data['high'].iloc[i])
                    current_ep = data['low'].iloc[i]
                    current_af = af_start
                else:
                    current_trend = 1
                    # Atualizar EP se tiver novo máximo
                    if data['high'].iloc[i] > prev_ep:
                        current_ep = data['high'].iloc[i]
                        current_af = min(prev_af + af_increment, af_max)
                    else:
                        current_ep = prev_ep
                        current_af = prev_af
            
            # Tendência de baixa
            else:
                # Limitar o PSAR pelos máximos anteriores
                current_psar = max(current_psar, data['high'].iloc[i-2], data['high'].iloc[i-1])
                
                # Verificar se o PSAR é ultrapassado (tendência invertida)
                if current_psar < data['high'].iloc[i]:
                    current_trend = 1
                    current_psar = min(data['low'].iloc[i-2], data['low'].iloc[i-1], data['low'].iloc[i])
                    current_ep = data['high'].iloc[i]
                    current_af = af_start
                else:
                    current_trend = -1
                    # Atualizar EP se tiver novo mínimo
                    if data['low'].iloc[i] < prev_ep:
                        current_ep = data['low'].iloc[i]
                        current_af = min(prev_af + af_increment, af_max)
                    else:
                        current_ep = prev_ep
                        current_af = prev_af
            
            # Armazenar valores
            data.loc[data.index[i], 'psar'] = current_psar
            data.loc[data.index[i], 'trend'] = current_trend
            data.loc[data.index[i], 'af'] = current_af
            data.loc[data.index[i], 'ep'] = current_ep
        
        return data['psar']
    @staticmethod
    def getROC(data, period=12):
        """
        Calcula o indicador ROC (Rate of Change)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do ROC
        
        Retorno:
        - roc: Série com os valores do Rate of Change
        """
        # Verificar se temos a coluna necessária
        if 'close' not in data.columns:
            raise ValueError("Coluna 'close' é necessária para o cálculo do ROC")
        
        # Calcular o ROC
        # ROC = ((Preço atual / Preço n períodos atrás) - 1) * 100
        roc = ((data['close'] / data['close'].shift(period)) - 1) * 100
        
        return roc
    @staticmethod
    def getSchaffTrendCycle(data, stc_fast=23, stc_slow=50, stc_cycle=10, use_close=True):
        """
        Calcula o indicador Schaff Trend Cycle
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - stc_fast: Período para MACD rápido
        - stc_slow: Período para MACD lento
        - stc_cycle: Período para o ciclo
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - stc: Série com os valores do Schaff Trend Cycle
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular MACD
        ema_fast = data[price_col].ewm(span=stc_fast, adjust=False).mean()
        ema_slow = data[price_col].ewm(span=stc_slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        
        # Calcular os máximos e mínimos do MACD ao longo do período do ciclo
        data = data.copy()
        data['macd'] = macd
        data['macd_max'] = data['macd'].rolling(window=stc_cycle).max()
        data['macd_min'] = data['macd'].rolling(window=stc_cycle).min()
        
        # Calcular o %K do MACD (similar ao Estocástico)
        # Evitar divisão por zero
        data['macd_range'] = data['macd_max'] - data['macd_min']
        data['macd_range'] = data['macd_range'].replace(0, np.finfo(float).eps)
        
        data['macd_k'] = 100 * (data['macd'] - data['macd_min']) / data['macd_range']
        
        # Calcular o %D do MACD (primeira suavização)
        data['macd_d'] = data['macd_k'].ewm(span=stc_cycle, adjust=False).mean()
        
        # Calcular máximos e mínimos do %D ao longo do período do ciclo
        data['macd_d_max'] = data['macd_d'].rolling(window=stc_cycle).max()
        data['macd_d_min'] = data['macd_d'].rolling(window=stc_cycle).min()
        
        # Calcular o Schaff Trend Cycle (segunda aplicação do estocástico)
        # Evitar divisão por zero
        data['macd_d_range'] = data['macd_d_max'] - data['macd_d_min']
        data['macd_d_range'] = data['macd_d_range'].replace(0, np.finfo(float).eps)
        
        data['stc'] = 100 * (data['macd_d'] - data['macd_d_min']) / data['macd_d_range']
        
        # Suavização final do STC
        stc_smooth = data['stc'].ewm(span=3, adjust=False).mean()
        
        return stc_smooth
    @staticmethod
    def getT3MovingAverage(data, period=14, volume_factor=0.7, use_close=True):
        """
        Calcula o indicador T3 Moving Average (Tillson T3)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do T3
        - volume_factor: Fator de volume (0-1)
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - t3: Série com os valores do T3 Moving Average
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular o fator de suavização (c1)
        c1 = -volume_factor * volume_factor * volume_factor
        
        # Calcular EMA 1
        e1 = data[price_col].ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 2
        e2 = e1.ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 3
        e3 = e2.ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 4
        e4 = e3.ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 5
        e5 = e4.ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 6
        e6 = e5.ewm(span=period, adjust=False).mean()
        
        # Calcular T3 usando a fórmula de Tillson
        t3 = c1 * e6 + 3 * volume_factor * c1 * e5 + 3 * volume_factor * volume_factor * c1 * e4 + volume_factor * volume_factor * volume_factor * e3
        
        return t3@staticmethod
    def getTEMA(data, period=14, use_close=True):
        """
        Calcula o indicador TEMA (Triple Exponential Moving Average)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do TEMA
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - tema: Série com os valores do TEMA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular EMA 1 (EMA do preço)
        ema1 = data[price_col].ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 2 (EMA do EMA1)
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        
        # Calcular EMA 3 (EMA do EMA2)
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        
        # Calcular TEMA = 3*EMA1 - 3*EMA2 + EMA3
        tema = 3 * ema1 - 3 * ema2 + ema3
        
        return tema
    @staticmethod
    def getTimeSeriesForecast(data, period=14, forecast_periods=1, use_close=True):
        """
        Calcula o indicador Time Series Forecast
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo da regressão linear
        - forecast_periods: Número de períodos no futuro para previsão
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - tsf: Série com os valores da previsão
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Inicializar a série de resultado
        tsf = pd.Series(index=data.index)
        
        # Para cada ponto, calcular a regressão linear para os 'period' pontos anteriores
        for i in range(period, len(data) + 1):
            if i < len(data):  # garantir que não estamos fora dos limites
                # Dados para a regressão
                y = data[price_col].iloc[i-period:i].values
                x = np.arange(period)
                
                # Calcular a regressão linear
                slope, intercept = np.polyfit(x, y, 1)
                
                # Valor da previsão 'forecast_periods' à frente
                forecast_value = intercept + slope * (period - 1 + forecast_periods)
                
                # Armazenar o valor
                tsf.iloc[i-1] = forecast_value
        
        return tsf
    @staticmethod
    def getTriangularMovingAverage(data, period=14, use_close=True):
        """
        Calcula o indicador Triangular Moving Average (TMA)
        
        Parâmetros:
        - data: DataFrame com os dados de preço
        - period: Período para cálculo do TMA
        - use_close: Usar preço de fechamento para cálculos
        
        Retorno:
        - tma: Série com os valores do TMA
        """
        price_col = 'close' if use_close else 'open'
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
        
        # Calcular a primeira média móvel simples (SMA)
        sma = data[price_col].rolling(window=period).mean()
        
        # Calcular a média móvel triangular (média móvel da média móvel)
        tma = sma.rolling(window=period).mean()
        
        return tma
    
    