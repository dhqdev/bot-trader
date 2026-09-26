import pandas as pd
import numpy as np

def donchianChannel(data, period=20):
    """
    Calcula o indicador Donchian Channel
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo das bandas de Donchian (padrão=20)
    
    Retorno:
    upper_band, middle_band, lower_band: Séries com os valores das bandas de Donchian
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a banda superior (máximo do período)
    upper_band = df[high_col].rolling(window=period).max()
    
    # Calcular a banda inferior (mínimo do período)
    lower_band = df[low_col].rolling(window=period).min()
    
    # Calcular a banda do meio (média das bandas superior e inferior)
    middle_band = (upper_band + lower_band) / 2
    
    return upper_band, middle_band, lower_band