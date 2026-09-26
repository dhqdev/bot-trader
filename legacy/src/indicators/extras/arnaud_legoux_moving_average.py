import pandas as pd
import numpy as np

def arnaudLegouxMovingAverage(data, period=14, sigma=6.0, offset=0.85, use_close=True):
    """
    Calcula o indicador Arnaud Legoux Moving Average
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do ALMA (padrão=14)
    - sigma: Controla a suavidade da curva (padrão=6.0)
    - offset: Controla a reatividade vs lag (0=mais lag, 1=mais reatividade) (padrão=0.85)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    alma: Série com os valores do ALMA
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
    
    # Verificar se temos dados suficientes
    if len(data) < period:
        return pd.Series(np.nan, index=data.index)
    
    # Calcular os parâmetros para o ALMA
    m = np.floor(offset * (period - 1))  # Controla o deslocamento da gaussiana
    s = period / sigma  # Controla a largura da gaussiana
    
    # Inicializar pesos
    weights = np.zeros(period)
    
    # Calcular pesos de acordo com a distribuição de Gauss
    for i in range(period):
        weights[i] = np.exp(-((i - m) ** 2) / (2 * s * s))
    
    # Normalizar pesos para que somem 1
    weights = weights / np.sum(weights)
    
    # Inicializar resultado com valores NaN
    alma_values = np.full(len(data), np.nan)
    
    # Aplicar ALMA para cada ponto, começando no índice 'period-1'
    for i in range(period - 1, len(data)):
        window = data[price_col].iloc[i - period + 1 : i + 1].values
        alma_values[i] = np.sum(window * weights[::-1])  # Inverter pesos para corresponder ao janelamento correto
    
    return pd.Series(alma_values, index=data.index)