import pandas as pd
import numpy as np

def priceChannels(data, period=20):
    """
    Calcula o indicador Price Channels
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo dos canais de preço (padrão=20)
    
    Retorno:
    upper, lower: Séries com os valores dos canais de preço
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o canal superior (máximo do período)
    upper = df[high_col].rolling(window=period).max()
    
    # Calcular o canal inferior (mínimo do período)
    lower = df[low_col].rolling(window=period).min()
    
    return upper, lower