import pandas as pd
import numpy as np

def schaffTrendCycle(data, stc_fast=23, stc_slow=50, stc_cycle=10, use_close=True):
    """
    Calcula o indicador Schaff Trend Cycle
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - stc_fast: Período rápido do MACD (padrão=23)
    - stc_slow: Período lento do MACD (padrão=50)
    - stc_cycle: Período do ciclo do Schaff (padrão=10)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    stc: Série com os valores do Schaff Trend Cycle
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
    
    # Calcular componentes do MACD
    ema_fast = df[price_col].ewm(span=stc_fast, adjust=False).mean()
    ema_slow = df[price_col].ewm(span=stc_slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    
    # Calcular máximos e mínimos do MACD ao longo do período do ciclo
    macd_max = macd.rolling(window=stc_cycle).max()
    macd_min = macd.rolling(window=stc_cycle).min()
    
    # Calcular o %K do MACD (similar ao Estocástico)
    # Evitar divisão por zero
    macd_diff = macd_max - macd_min
    macd_diff = macd_diff.replace(0, 0.0001)
    
    macd_k = 100 * (macd - macd_min) / macd_diff
    
    # Calcular o %D do MACD (primeira suavização)
    macd_d = macd_k.ewm(span=stc_cycle, adjust=False).mean()
    
    # Calcular máximos e mínimos do %D ao longo do período do ciclo
    macd_d_max = macd_d.rolling(window=stc_cycle).max()
    macd_d_min = macd_d.rolling(window=stc_cycle).min()
    
    # Calcular o Schaff Trend Cycle (segunda aplicação do estocástico)
    # Evitar divisão por zero
    macd_d_diff = macd_d_max - macd_d_min
    macd_d_diff = macd_d_diff.replace(0, 0.0001)
    
    stc = 100 * (macd_d - macd_d_min) / macd_d_diff
    
    # Suavização final do STC
    stc = stc.ewm(span=3, adjust=False).mean()
    
    return stc