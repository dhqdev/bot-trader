import pandas as pd
import numpy as np

def cmf(data, period=20):
    """
    Calcula o indicador CMF (Chaikin Money Flow)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    - period: Período para cálculo do CMF (padrão=20)
    
    Retorno:
    cmf: Série com os valores do Chaikin Money Flow
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    volume_col = 'volume' if 'volume' in data.columns else 'volume'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o Money Flow Multiplier
    df['mf_multiplier'] = ((df[close_col] - df[low_col]) - 
                          (df[high_col] - df[close_col])) / \
                          (df[high_col] - df[low_col])
    
    # Lidar com casos onde high == low (evitar divisão por zero)
    df['mf_multiplier'] = df['mf_multiplier'].replace([np.inf, -np.inf], 0)
    df['mf_multiplier'] = df['mf_multiplier'].fillna(0)
    
    # Calcular o Money Flow Volume
    df['mf_volume'] = df['mf_multiplier'] * df[volume_col]
    
    # Calcular o Chaikin Money Flow
    cmf_values = df['mf_volume'].rolling(window=period).sum() / df[volume_col].rolling(window=period).sum()
    
    # Preencher valores NaN ou infinitos
    cmf_values = cmf_values.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    return cmf_values