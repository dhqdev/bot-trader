import pandas as pd
import numpy as np

def ehlerFisherTransform(data, period=10):
    """
    Calcula o indicador Ehler Fisher Transform
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Ehler Fisher Transform (padrão=10)
    
    Retorno:
    fisher_transform: Série com os valores do Ehler Fisher Transform
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
    
    # Iniciar valores para máximo e mínimo
    df['max_h'] = np.nan
    df['min_l'] = np.nan
    
    # Preencher a primeira linha com valores iniciais para evitar NaN
    if len(df) > 0:
        df.loc[df.index[0], 'max_h'] = df.loc[df.index[0], 'price_mid']
        df.loc[df.index[0], 'min_l'] = df.loc[df.index[0], 'price_mid']
    
    # Calcular máximos e mínimos com um método adaptativo (Ehlers)
    # Isso usa uma técnica de alisamento que é mais responsiva a mudanças recentes
    alpha = 2.0 / (period + 1.0)
    
    for i in range(1, len(df)):
        # Atualizar máximo
        max_value = df.loc[df.index[i-1], 'max_h']
        if df.loc[df.index[i], 'price_mid'] > max_value:
            max_value = df.loc[df.index[i], 'price_mid']
        else:
            max_value = max_value - alpha * (max_value - df.loc[df.index[i], 'price_mid'])
        df.loc[df.index[i], 'max_h'] = max_value
        
        # Atualizar mínimo
        min_value = df.loc[df.index[i-1], 'min_l']
        if df.loc[df.index[i], 'price_mid'] < min_value:
            min_value = df.loc[df.index[i], 'price_mid']
        else:
            min_value = min_value + alpha * (df.loc[df.index[i], 'price_mid'] - min_value)
        df.loc[df.index[i], 'min_l'] = min_value
    
    # Normalizar os preços para o intervalo [-1, 1]
    df['value'] = np.nan
    
    # Calcular o valor normalizado
    for i in range(1, len(df)):
        price_range = df.loc[df.index[i], 'max_h'] - df.loc[df.index[i], 'min_l']
        if price_range == 0:
            df.loc[df.index[i], 'value'] = 0
        else:
            # Fórmula de Ehlers para normalização
            df.loc[df.index[i], 'value'] = 2 * ((df.loc[df.index[i], 'price_mid'] - df.loc[df.index[i], 'min_l']) / price_range - 0.5)
    
    # Suavizar o valor normalizado com uma média móvel
    df['smooth_value'] = df['value'].rolling(window=period).mean().fillna(0)
    
    # Limitar o valor a +/- 0.999 para evitar infinitos na transformação
    df['smooth_value'] = np.clip(df['smooth_value'], -0.999, 0.999)
    
    # Aplicar a transformação de Fisher
    fisher_transform = 0.5 * np.log((1 + df['smooth_value']) / (1 - df['smooth_value']))
    
    return fisher_transform