import pandas as pd
import numpy as np

def kama(data, period=14, fast_ema=2, slow_ema=30):
    """
    Calcula o indicador KAMA (Kaufman's Adaptive Moving Average)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Efficiency Ratio (padrão=14)
    - fast_ema: Período rápido para o Efficiency Ratio (padrão=2)
    - slow_ema: Período lento para o Efficiency Ratio (padrão=30)
    
    Retorno:
    kama: Série com os valores do KAMA
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular a mudança de preço direta
    df['price_change'] = df[close_col].diff(1)
    
    # Calcular o "Efficiency Ratio" (ER)
    df['direction'] = abs(df[close_col] - df[close_col].shift(period))
    df['volatility'] = abs(df['price_change']).rolling(window=period).sum()
    
    # Evitar divisão por zero
    df['volatility'] = df['volatility'].replace(0, np.nan)
    df['efficiency_ratio'] = df['direction'] / df['volatility']
    
    # Substituir valores NaN e infinitos no ER
    df['efficiency_ratio'] = df['efficiency_ratio'].replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # Calcular as constantes suavizadas
    fast_sc = 2.0 / (fast_ema + 1.0)
    slow_sc = 2.0 / (slow_ema + 1.0)
    
    # Calcular o fator de suavização
    df['smooth_factor'] = (df['efficiency_ratio'] * (fast_sc - slow_sc) + slow_sc) ** 2
    
    # Inicializar o KAMA
    kama_values = np.zeros(len(df))
    kama_values[:] = np.nan
    
    # Definir o primeiro valor KAMA
    # Normalmente, seria a média dos primeiros 'period' valores
    if len(df) > period:
        # O primeiro valor é o preço atual
        kama_values[period-1] = df[close_col].iloc[period-1]
    
    # Calcular o KAMA para os pontos restantes
    for i in range(period, len(df)):
        prev_kama = kama_values[i-1]
        if np.isnan(prev_kama):
            kama_values[i] = df[close_col].iloc[i]
        else:
            current_sf = df['smooth_factor'].iloc[i]
            current_close = df[close_col].iloc[i]
            kama_values[i] = prev_kama + current_sf * (current_close - prev_kama)
    
    return pd.Series(kama_values, index=df.index)