import pandas as pd
import numpy as np

def hullMovingAverage(data, period=14, use_close=True):
    """
    Calcula o indicador Hull Moving Average
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do HMA (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    hma: Série com os valores do Hull Moving Average
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
    
    # Função para calcular a WMA (Weighted Moving Average)
    def calculate_wma(series, period):
        weights = np.arange(1, period + 1)
        wma = series.rolling(window=period).apply(
            lambda x: np.sum(weights * x) / np.sum(weights), raw=True
        )
        return wma
    
    # Calcular o Hull Moving Average
    # 1. Calcular WMA com período original
    wma_full = calculate_wma(df[price_col], period)
    
    # 2. Calcular WMA com período metade do original
    period_half = period // 2
    wma_half = calculate_wma(df[price_col], period_half)
    
    # 3. Calcular o raw HMA
    raw_hma = 2 * wma_half - wma_full
    
    # 4. Calcular o HMA final
    sqrt_period = int(np.sqrt(period))
    hma = calculate_wma(raw_hma, sqrt_period)
    
    return hma