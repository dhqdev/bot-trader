import pandas as pd
import numpy as np

def obv(data):
    """
    Calcula o indicador OBV (On Balance Volume)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    
    Retorno:
    obv: Série com os valores do On Balance Volume
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
    df['price_change'] = df[close_col].diff()
    
    # Inicializar o OBV
    obv_values = pd.Series(0, index=df.index)
    
    # Preencher o primeiro valor com o volume inicial
    if len(df) > 0:
        obv_values.iloc[0] = df[volume_col].iloc[0]
    
    # Calcular o OBV para os dias seguintes
    for i in range(1, len(df)):
        if df['price_change'].iloc[i] > 0:
            # Preço subiu: adicionar volume
            obv_values.iloc[i] = obv_values.iloc[i-1] + df[volume_col].iloc[i]
        elif df['price_change'].iloc[i] < 0:
            # Preço caiu: subtrair volume
            obv_values.iloc[i] = obv_values.iloc[i-1] - df[volume_col].iloc[i]
        else:
            # Preço não mudou: manter o mesmo OBV
            obv_values.iloc[i] = obv_values.iloc[i-1]
    
    return obv_values