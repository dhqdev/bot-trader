import pandas as pd
import numpy as np

def wma(data, period=14, use_close=True):
    """
    Calcula o indicador WMA (Weighted Moving Average)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do WMA (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    wma: Série com os valores do WMA
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
    
    # Função para calcular o WMA
    def calculate_wma(series, period):
        # Criar array de pesos, com maior peso para os valores mais recentes
        weights = np.arange(1, period + 1)
        
        # Aplicar os pesos para cada janela
        wma_values = series.rolling(window=period).apply(
            lambda x: np.sum(weights * x) / np.sum(weights), raw=True
        )
        
        return wma_values
    
    # Calcular o WMA
    wma_values = calculate_wma(df[price_col], period)
    
    return wma_values