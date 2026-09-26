import pandas as pd
import numpy as np

def keltnerChannels(data, period=14, atr_period=10, multiplier=2.0, use_ema=True):
    """
    Calcula o indicador Keltner Channels
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo da média móvel (padrão=14)
    - atr_period: Período para cálculo do ATR (padrão=10)
    - multiplier: Multiplicador para determinar a largura das bandas (padrão=2.0)
    - use_ema: Se True, utiliza EMA para a linha central; caso contrário utiliza SMA (padrão=True)
    
    Retorno:
    middle_line, upper_band, lower_band: Séries com os valores das bandas de Keltner
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a linha do meio (EMA ou SMA do preço de fechamento)
    if use_ema:
        middle_line = df[close_col].ewm(span=period, adjust=False).mean()
    else:
        middle_line = df[close_col].rolling(window=period).mean()
    
    # Calcular o True Range (TR)
    df['prev_close'] = df[close_col].shift(1)
    df['tr1'] = abs(df[high_col] - df[low_col])
    df['tr2'] = abs(df[high_col] - df['prev_close'])
    df['tr3'] = abs(df[low_col] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # Calcular o ATR (Average True Range)
    atr = df['tr'].rolling(window=atr_period).mean()
    
    # Calcular as bandas superiores e inferiores
    upper_band = middle_line + (multiplier * atr)
    lower_band = middle_line - (multiplier * atr)
    
    return middle_line, upper_band, lower_band