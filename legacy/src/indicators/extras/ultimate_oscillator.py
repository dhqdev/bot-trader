import pandas as pd
import numpy as np

def ultimateOscillator(data, period1=7, period2=14, period3=28):
    """
    Calcula o indicador Ultimate Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period1: Primeiro período (curto) para média (padrão=7)
    - period2: Segundo período (médio) para média (padrão=14)
    - period3: Terceiro período (longo) para média (padrão=28)
    
    Retorno:
    ultimate_oscillator: Série com os valores do Ultimate Oscillator
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
    
    # Calcular True Range (TR)
    data['prev_close'] = data[close_col].shift(1)
    
    # True Range = max(high, prev_close) - min(low, prev_close)
    data['tr'] = data.apply(
        lambda x: max(x[high_col], x['prev_close']) - min(x[low_col], x['prev_close']) 
        if not pd.isna(x['prev_close']) else x[high_col] - x[low_col],
        axis=1
    )
    
    # Buying Pressure = close - min(low, prev_close)
    data['bp'] = data.apply(
        lambda x: x[close_col] - min(x[low_col], x['prev_close'])
        if not pd.isna(x['prev_close']) else x[close_col] - x[low_col],
        axis=1
    )
    
    # Calcular as médias móveis para diferentes períodos
    # Average1 = Sum(BP, period1) / Sum(TR, period1)
    data['avg1'] = data['bp'].rolling(window=period1).sum() / data['tr'].rolling(window=period1).sum()
    
    # Average2 = Sum(BP, period2) / Sum(TR, period2)
    data['avg2'] = data['bp'].rolling(window=period2).sum() / data['tr'].rolling(window=period2).sum()
    
    # Average3 = Sum(BP, period3) / Sum(TR, period3)
    data['avg3'] = data['bp'].rolling(window=period3).sum() / data['tr'].rolling(window=period3).sum()
    
    # Calcular o Ultimate Oscillator com pesos padrão
    weight1 = 4.0
    weight2 = 2.0
    weight3 = 1.0
    total_weight = weight1 + weight2 + weight3
    
    # UO = 100 * ((weight1 * Average1) + (weight2 * Average2) + (weight3 * Average3)) / (weight1 + weight2 + weight3)
    ultimate_oscillator = 100 * ((weight1 * data['avg1'] + 
                                weight2 * data['avg2'] + 
                                weight3 * data['avg3']) / total_weight)
    
    return ultimate_oscillator