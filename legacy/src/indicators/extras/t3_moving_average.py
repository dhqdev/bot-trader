import pandas as pd
import numpy as np

def t3MovingAverage(data, period=14, volume_factor=0.7, use_close=True):
    """
    Calcula o indicador T3 Moving Average
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do T3 (padrão=14)
    - volume_factor: Fator de volume (0-1, padrão=0.7)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    t3: Série com os valores do T3 Moving Average
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
    
    # Calcular o fator de suavização (c1)
    c1 = -volume_factor * volume_factor * volume_factor
    
    # Calcular EMA 1
    e1 = df[price_col].ewm(span=period, adjust=False).mean()
    
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
    
    return t3