import pandas as pd
import numpy as np

def movingAverageEnvelope(data, period=14, envelope_percentage=2.5, use_ema=False):
    """
    Calcula o indicador Moving Average Envelope
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo da média móvel (padrão=14)
    - envelope_percentage: Percentual para determinar as bandas (padrão=2.5)
    - use_ema: Se True, utiliza EMA; caso contrário, utiliza SMA (padrão=False)
    
    Retorno:
    middle, upper, lower: Séries com os valores do Moving Average Envelope
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
    
    # Calcular a média móvel (EMA ou SMA) do preço de fechamento
    if use_ema:
        middle = df[close_col].ewm(span=period, adjust=False).mean()
    else:
        middle = df[close_col].rolling(window=period).mean()
    
    # Converter o percentual para decimal
    envelope_factor = envelope_percentage / 100.0
    
    # Calcular as bandas superior e inferior
    upper = middle * (1 + envelope_factor)
    lower = middle * (1 - envelope_factor)
    
    return middle, upper, lower