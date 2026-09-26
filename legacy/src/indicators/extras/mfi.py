import pandas as pd
import numpy as np

def mfi(data, period=14):
    """
    Calcula o indicador MFI (Money Flow Index)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    - period: Período para cálculo do MFI (padrão=14)
    
    Retorno:
    mfi: Série com os valores do Money Flow Index
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
    
    # Calcular o preço típico
    df['typical_price'] = (df[high_col] + df[low_col] + df[close_col]) / 3
    
    # Calcular o fluxo de dinheiro (money flow)
    df['money_flow'] = df['typical_price'] * df[volume_col]
    
    # Calcular a mudança do preço típico
    df['price_change'] = df['typical_price'].diff()
    
    # Separar fluxo de dinheiro positivo e negativo
    df['positive_flow'] = np.where(df['price_change'] > 0, df['money_flow'], 0)
    df['negative_flow'] = np.where(df['price_change'] < 0, df['money_flow'], 0)
    
    # Calcular a soma dos fluxos positivos e negativos para o período
    df['positive_flow_sum'] = df['positive_flow'].rolling(window=period).sum()
    df['negative_flow_sum'] = df['negative_flow'].rolling(window=period).sum()
    
    # Calcular o Money Ratio
    df['money_ratio'] = df['positive_flow_sum'] / df['negative_flow_sum']
    
    # Substituir valores infinitos ou NaN (caso soma negativa seja zero)
    df['money_ratio'] = df['money_ratio'].replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # Calcular o MFI
    mfi_values = 100 - (100 / (1 + df['money_ratio']))
    
    return mfi_values