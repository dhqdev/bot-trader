import pandas as pd
import numpy as np

def marketFacilitationIndex(data):
    """
    Calcula o indicador Market Facilitation Index
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    
    Retorno:
    mfi: Série com os valores do Market Facilitation Index
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'volume']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    volume_col = 'volume' if 'volume' in data.columns else 'volume'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o Market Facilitation Index (MFI)
    # MFI = (High - Low) / Volume
    mfi = (df[high_col] - df[low_col]) / df[volume_col]
    
    # Substituir valores infinitos ou NaN (caso volume seja zero)
    mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    return mfi