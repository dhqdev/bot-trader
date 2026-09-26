import pandas as pd
import numpy as np

def fractals(data, window=2):
    """
    Calcula o indicador Fractals
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - window: Tamanho da janela para identificar fractais (padrão=2)
    
    Retorno:
    fractal_up, fractal_down: Séries com os valores dos fractais
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
    
    # Inicializar séries para fractais
    fractal_up = pd.Series(0, index=df.index)
    fractal_down = pd.Series(0, index=df.index)
    
    # Tamanho da janela completa (window barras para cada lado + 1 para o centro)
    full_window = 2 * window + 1
    
    # Verificar se temos dados suficientes
    if len(df) < full_window:
        return fractal_up, fractal_down
    
    # Identificar fractais
    for i in range(window, len(df) - window):
        # Verificar se é um fractal de alta (high point)
        high_values_left = df[high_col].iloc[i-window:i]
        high_values_right = df[high_col].iloc[i+1:i+window+1]
        
        if df[high_col].iloc[i] > high_values_left.max() and df[high_col].iloc[i] > high_values_right.max():
            fractal_up.iloc[i] = df[high_col].iloc[i]
        
        # Verificar se é um fractal de baixa (low point)
        low_values_left = df[low_col].iloc[i-window:i]
        low_values_right = df[low_col].iloc[i+1:i+window+1]
        
        if df[low_col].iloc[i] < low_values_left.min() and df[low_col].iloc[i] < low_values_right.min():
            fractal_down.iloc[i] = df[low_col].iloc[i]
    
    return fractal_up, fractal_down