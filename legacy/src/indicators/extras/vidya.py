import pandas as pd
import numpy as np

def vidya(data, period=14, chande_period=10, use_close=True):
    """
    Calcula o indicador VIDYA (Variable Index Dynamic Average)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do VIDYA (padrão=14)
    - chande_period: Período para cálculo do Chande Momentum Oscillator (padrão=10)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    vidya: Série com os valores do VIDYA
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
    
    # Calcular variação diária
    price_change = data[price_col].diff()
    
    # Separar as variações positivas e negativas
    gain = np.where(price_change > 0, price_change, 0)
    loss = np.where(price_change < 0, -price_change, 0)
    
    # Calcular a soma das variações positivas e negativas para o período
    sum_gains = pd.Series(gain).rolling(window=chande_period).sum()
    sum_losses = pd.Series(loss).rolling(window=chande_period).sum()
    
    # Calcular o Chande Momentum Oscillator (CMO)
    cmo = 100 * ((sum_gains - sum_losses) / (sum_gains + sum_losses))
    
    # Substituir valores NaN ou infinitos
    cmo = cmo.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # Calcular o VIDYA
    # Fator de suavização tradicional do EMA: 2 / (period + 1)
    sc = 2 / (period + 1)
    
    # Normalizar o CMO para o range 0-1
    k = abs(cmo) / 100
    
    # Inicializar VIDYA como uma série de zeros
    vidya_values = np.zeros(len(data))
    vidya_values[:] = np.nan
    
    # Encontrar o primeiro índice válido
    first_valid_idx = cmo.first_valid_index()
    if first_valid_idx is not None:
        idx = data.index.get_loc(first_valid_idx)
        # Inicializar VIDYA com o primeiro valor de preço
        vidya_values[idx] = data[price_col].iloc[idx]
        
        # Calcular VIDYA para os valores restantes
        for i in range(idx + 1, len(data)):
            # Fator de suavização ajustado pela volatilidade (k)
            alpha = sc * k.iloc[i]
            # VIDYA(i) = VIDYA(i-1) + α * (Price(i) - VIDYA(i-1))
            vidya_values[i] = vidya_values[i-1] + alpha * (data[price_col].iloc[i] - vidya_values[i-1])
    
    vidya_series = pd.Series(vidya_values, index=data.index)
    
    return vidya_series