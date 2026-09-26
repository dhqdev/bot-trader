import pandas as pd
import numpy as np

def timeSeriesForecast(data, period=14, forecast_periods=1, use_close=True):
    """
    Calcula o indicador Time Series Forecast
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo da regressão linear (padrão=14)
    - forecast_periods: Períodos à frente para previsão (padrão=1)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    tsf: Série com os valores do Time Series Forecast
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
    
    # Função para calcular a previsão de regressão linear para um ponto no futuro
    def linear_regression_forecast(series, period, forecast_periods=1):
        # Criar array de índices (x) para a regressão
        x = np.arange(period)
        # Inicializar array para os resultados
        result = np.zeros(len(series))
        result[:] = np.nan
        
        # Percorrer a série para calcular a regressão para cada janela
        for i in range(period - 1, len(series)):
            # Obter os últimos 'period' valores (y)
            y = series.iloc[i - period + 1:i + 1].values
            
            # Calcular a regressão linear (mx + b)
            m, b = np.polyfit(x, y, 1)
            
            # Calcular o valor previsto para 'forecast_periods' à frente
            forecast = m * (period - 1 + forecast_periods) + b
            result[i] = forecast
        
        return pd.Series(result, index=series.index)
    
    # Calcular o Time Series Forecast (previsão n períodos à frente)
    tsf = linear_regression_forecast(df[price_col], period, forecast_periods)
    
    return tsf