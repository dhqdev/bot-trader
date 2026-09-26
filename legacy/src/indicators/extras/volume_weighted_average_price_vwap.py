import pandas as pd
import numpy as np

def volumeWeightedAveragePrice(data, period=14, reset_daily=True):
    """
    Calcula o indicador Volume-Weighted Average Price (VWAP)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço e volume
    - period: Período para cálculo se não estiver usando reset diário (padrão=14)
    - reset_daily: Se True, reseta os cálculos a cada dia de negociação
    
    Retorno:
    vwap, upper_band, lower_band: Séries com os valores do VWAP e suas bandas
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
    
    # Calcular o preço típico (high + low + close) / 3
    df['typical_price'] = (df[high_col] + df[low_col] + df[close_col]) / 3
    
    # Calcular o valor negociado (preço típico * volume)
    df['tp_volume'] = df['typical_price'] * df[volume_col]
    
    # Verificar se temos a data para separar dias
    date_column = None
    for col in ['date', 'datetime', 'timestamp']:
        if col in df.columns:
            date_column = col
            break
    
    # Se resetar diariamente e temos uma coluna de data
    if reset_daily and date_column:
        # Extrair apenas a data (sem hora) para agrupar por dia
        if pd.api.types.is_datetime64_any_dtype(df[date_column]):
            df['day'] = df[date_column].dt.date
        else:
            # Tentar converter para datetime
            try:
                df['day'] = pd.to_datetime(df[date_column]).dt.date
            except:
                # Se não conseguir converter, usar o dia do index (se for datetime)
                if pd.api.types.is_datetime64_any_dtype(df.index):
                    df['day'] = df.index.date
                else:
                    # Se tudo falhar, não resetar diariamente
                    reset_daily = False
    
    # Calcular o VWAP
    if reset_daily and 'day' in df.columns:
        # Resetar os cálculos por dia
        df['cum_tp_volume'] = df.groupby('day')['tp_volume'].cumsum()
        df['cum_volume'] = df.groupby('day')[volume_col].cumsum()
    else:
        # Usar janela móvel se não estiver resetando diariamente
        if not reset_daily:
            # Janela móvel para o período especificado
            df['cum_tp_volume'] = df['tp_volume'].rolling(window=period).sum()
            df['cum_volume'] = df[volume_col].rolling(window=period).sum()
        else:
            # Acumular continuamente se resetar diariamente mas não tiver coluna de data
            df['cum_tp_volume'] = df['tp_volume'].cumsum()
            df['cum_volume'] = df[volume_col].cumsum()
    
    # Evitar divisão por zero
    df['vwap'] = np.where(
        df['cum_volume'] > 0,
        df['cum_tp_volume'] / df['cum_volume'],
        df['typical_price']
    )
    
    # Calcular desvio do preço em relação ao VWAP
    df['price_dev'] = df['typical_price'] - df['vwap']
    
    # Calcular desvio padrão do preço em relação ao VWAP
    if reset_daily and 'day' in df.columns:
        df['std_dev'] = df.groupby('day')['price_dev'].rolling(window=period).std().reset_index(level=0, drop=True)
    else:
        df['std_dev'] = df['price_dev'].rolling(window=period).std()
    
    # Preencher valores NaN
    df['std_dev'] = df['std_dev'].fillna(0)
    
    # Multiplicador padrão para as bandas
    multiplier = 1.0
    
    # Calcular bandas de desvio padrão
    upper_band = df['vwap'] + (df['std_dev'] * multiplier)
    lower_band = df['vwap'] - (df['std_dev'] * multiplier)
    
    return df['vwap'], upper_band, lower_band