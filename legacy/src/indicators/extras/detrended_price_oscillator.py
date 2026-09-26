import pandas as pd
import numpy as np

def detrendedPriceOscillator(data, period=14, sma_period=15):
    """
    Calcula o indicador Detrended Price Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do DPO (padrão=14)
    - sma_period: Período para cálculo da média móvel simples (padrão=15)
    
    Retorno:
    dpo: Série com os valores do Detrended Price Oscillator
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a média móvel simples
    df['sma'] = df[close_col].rolling(window=sma_period).mean()
    
    # Calcular o DPO = Preço(i) - SMA(i - (period/2 + 1))
    # O deslocamento remove a tendência de longo prazo da média móvel
    shift_period = int(period / 2 + 1)
    dpo = df[close_col] - df['sma'].shift(shift_period)
    
    return dpo