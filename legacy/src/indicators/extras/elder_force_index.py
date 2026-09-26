import pandas as pd
import numpy as np

def elderForceIndex(data, period=13):
    """
    Calcula o indicador Elder Force Index
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    - period: Período para cálculo da média móvel exponencial (padrão=13)
    
    Retorno:
    force_index: Série com os valores do Elder Force Index
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['close', 'volume']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    volume_col = 'volume' if 'volume' in data.columns else 'volume'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a variação do preço
    df['price_change'] = df[close_col].diff(1)
    
    # Calcular o Force Index raw (variação do preço * volume)
    df['force_index_raw'] = df['price_change'] * df[volume_col]
    
    # Calcular o Force Index suavizado com EMA
    force_index = df['force_index_raw'].ewm(span=period, adjust=False).mean()
    
    return force_index