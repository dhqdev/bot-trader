import pandas as pd
import numpy as np

def zeroLagMovingAverage(data, period=14, use_close=True):
    """
    Calcula o indicador Zero-Lag Moving Average (ZLEMA)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do ZLEMA (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    zlema: Série com os valores do ZLEMA
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Determinar qual coluna de preço usar
    price_col = 'close' if use_close else 'open'
    if price_col not in data.columns:
        price_col = price_col.lower()
        if price_col not in data.columns and price_col == 'open':
            # Caso 'open' não esteja disponível, usar 'close'
            price_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o lag (atraso) a ser removido
    lag = (period - 1) // 2
    
    # Verificar se temos dados suficientes
    if len(df) <= lag:
        return pd.Series(np.nan, index=df.index)
    
    # Entrada para o ZLEMA: 2 * preço atual - preço com lag
    df['zlema_input'] = 2 * df[price_col] - df[price_col].shift(lag)
    
    # Calcular o ZLEMA como um EMA da entrada calculada
    zlema = df['zlema_input'].ewm(span=period, adjust=False).mean()
    
    return zlema