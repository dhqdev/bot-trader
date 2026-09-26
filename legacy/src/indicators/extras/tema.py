import pandas as pd
import numpy as np

def tema(data, period=14, use_close=True):
    """
    Calcula o indicador TEMA (Triple Exponential Moving Average)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do TEMA (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    tema: Série com os valores do TEMA
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
    
    # Calcular o primeiro EMA
    ema1 = df[price_col].ewm(span=period, adjust=False).mean()
    
    # Calcular o segundo EMA (EMA do primeiro EMA)
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    
    # Calcular o terceiro EMA (EMA do segundo EMA)
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    
    # Calcular o TEMA = 3*EMA1 - 3*EMA2 + EMA3
    tema = 3 * ema1 - 3 * ema2 + ema3
    
    return tema