import pandas as pd
import numpy as np

def chaikinOscillator(data, fast_period=3, slow_period=10):
    """
    Calcula o indicador Chaikin Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    - fast_period: Período para a EMA rápida da ADL (padrão=3)
    - slow_period: Período para a EMA lenta da ADL (padrão=10)
    
    Retorno:
    chaikin_oscillator: Série com os valores do Chaikin Oscillator
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    volume_col = 'volume' if 'volume' in data.columns else 'volume'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o Money Flow Multiplier
    df['mf_multiplier'] = ((df[close_col] - df[low_col]) - 
                          (df[high_col] - df[close_col])) / \
                          (df[high_col] - df[low_col])
    
    # Lidar com casos onde high == low (evitar divisão por zero)
    df['mf_multiplier'] = df['mf_multiplier'].replace([np.inf, -np.inf], 0)
    df['mf_multiplier'] = df['mf_multiplier'].fillna(0)
    
    # Calcular o Money Flow Volume
    df['mf_volume'] = df['mf_multiplier'] * df[volume_col]
    
    # Calcular a Accumulation/Distribution Line (ADL)
    df['adl'] = df['mf_volume'].cumsum()
    
    # Calcular EMA rápida e lenta da ADL
    df['adl_ema_fast'] = df['adl'].ewm(span=fast_period, adjust=False).mean()
    df['adl_ema_slow'] = df['adl'].ewm(span=slow_period, adjust=False).mean()
    
    # Calcular o Chaikin Oscillator
    chaikin_oscillator = df['adl_ema_fast'] - df['adl_ema_slow']
    
    return chaikin_oscillator