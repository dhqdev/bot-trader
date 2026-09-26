import pandas as pd
import numpy as np

def triangularMovingAverage(data, period=14, use_close=True):
    """
    Calcula o indicador Triangular Moving Average
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do TMA (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    tma: Série com os valores do TMA
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
        if price_col not in data.columns and price_col == 'open':
            # Caso 'open' não esteja disponível, usar 'close'
            price_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o período para cada SMA
    n = round((period + 1) / 2)
    
    # Calcular a primeira SMA
    sma1 = df[price_col].rolling(window=n).mean()
    
    # Calcular a segunda SMA (média móvel da primeira SMA)
    tma = sma1.rolling(window=n).mean()
    
    return tma