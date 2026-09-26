import pandas as pd
import numpy as np

def trueStrengthIndex(data, r_period=25, s_period=13, signal_period=7, use_close=True):
    """
    Calcula o indicador True Strength Index
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - r_period: Período para a primeira suavização (padrão=25)
    - s_period: Período para a segunda suavização (padrão=13)
    - signal_period: Período para a linha de sinal (padrão=7)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    tsi, tsi_signal: Séries com os valores do TSI e sua linha de sinal
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Determinar qual coluna de preço usar
    price_col = 'close' if use_close else 'open'
    if price_col not in data.columns:
        price_col = price_col.lower()
        if price_col not in data.columns:
            raise ValueError(f"Coluna '{price_col}' não encontrada nos dados")
    
    # Calcular mudanças de preço
    price_change = data[price_col].diff()
    
    # Primeira suavização da mudança de preço (EMA do period r_period)
    pc_ema_r = price_change.ewm(span=r_period, adjust=False).mean()
    
    # Segunda suavização (EMA do resultado anterior de period s_period)
    pc_ema_r_s = pc_ema_r.ewm(span=s_period, adjust=False).mean()
    
    # Primeira suavização do valor absoluto da mudança de preço
    abs_pc_ema_r = price_change.abs().ewm(span=r_period, adjust=False).mean()
    
    # Segunda suavização do valor absoluto
    abs_pc_ema_r_s = abs_pc_ema_r.ewm(span=s_period, adjust=False).mean()
    
    # Calcular TSI
    tsi = 100 * (pc_ema_r_s / abs_pc_ema_r_s)
    
    # Calcular linha de sinal (EMA do TSI)
    tsi_signal = tsi.ewm(span=signal_period, adjust=False).mean()
    
    return tsi, tsi_signal