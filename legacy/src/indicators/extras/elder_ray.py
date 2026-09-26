import pandas as pd
import numpy as np

def elderRay(data, period=13):
    """
    Calcula o indicador Elder Ray
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo da média móvel exponencial (padrão=13)
    
    Retorno:
    bull_power, bear_power: Séries com os valores do Bull Power e Bear Power
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a média móvel exponencial do preço de fechamento
    df['ema'] = df[close_col].ewm(span=period, adjust=False).mean()
    
    # Calcular o Bull Power (High - EMA)
    bull_power = df[high_col] - df['ema']
    
    # Calcular o Bear Power (Low - EMA)
    bear_power = df[low_col] - df['ema']
    
    return bull_power, bear_power