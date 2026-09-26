import pandas as pd
import numpy as np

def fisherTransform(data, period=10):
    """
    Calcula o indicador Fisher Transform
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Fisher Transform (padrão=10)
    
    Retorno:
    fisher_transform: Série com os valores do Fisher Transform
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
    
    # Calcular o valor médio (midpoint) do período
    df['price_mid'] = (df[high_col] + df[low_col]) / 2
    
    # Encontrar o máximo e mínimo para o período
    df['period_high'] = df['price_mid'].rolling(window=period).max()
    df['period_low'] = df['price_mid'].rolling(window=period).min()
    
    # Normalizar os preços para o intervalo [-1, 1]
    df['value'] = np.nan
    
    # Evitar divisão por zero
    for i in range(period-1, len(df)):
        price_range = df['period_high'].iloc[i] - df['period_low'].iloc[i]
        if price_range == 0:
            df.loc[df.index[i], 'value'] = 0
        else:
            df.loc[df.index[i], 'value'] = 2 * ((df['price_mid'].iloc[i] - df['period_low'].iloc[i]) / price_range - 0.5)
    
    # Calcular o Fisher Transform
    df['fisher_input'] = df['value'].rolling(window=period).mean()
    
    # Limitar o valor a +/- 0.999 para evitar infinitos na transformação
    df['fisher_input'] = np.clip(df['fisher_input'], -0.999, 0.999)
    
    # Aplicar a transformação de Fisher
    fisher_transform = 0.5 * np.log((1 + df['fisher_input']) / (1 - df['fisher_input']))
    
    return fisher_transform