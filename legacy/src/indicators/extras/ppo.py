import pandas as pd
import numpy as np

def ppo(data, fast_period=12, slow_period=26, signal_period=9):
    """
    Calcula o indicador PPO (Percentage Price Oscillator)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - fast_period: Período para a EMA rápida (padrão=12)
    - slow_period: Período para a EMA lenta (padrão=26)
    - signal_period: Período para a linha de sinal (padrão=9)
    
    Retorno:
    ppo, ppo_signal, ppo_histogram: Séries com os valores do PPO
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular EMA rápida e lenta
    ema_fast = df[close_col].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df[close_col].ewm(span=slow_period, adjust=False).mean()
    
    # Calcular o PPO: ((EMA_Rápida - EMA_Lenta) / EMA_Lenta) * 100
    ppo = ((ema_fast - ema_slow) / ema_slow) * 100
    
    # Calcular a linha de sinal (EMA do PPO)
    ppo_signal = ppo.ewm(span=signal_period, adjust=False).mean()
    
    # Calcular o histograma do PPO
    ppo_histogram = ppo - ppo_signal
    
    return ppo, ppo_signal, ppo_histogram