import pandas as pd
import numpy as np

def linearRegression(data, period=14, use_close=True):
    """
    Calcula o indicador Linear Regression
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo da regressão linear (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    linear_reg: Série com os valores da regressão linear
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
    
    # Função para calcular a regressão linear para uma janela de dados
    def calculate_linear_regression(x, y):
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        # Calcular os coeficientes da regressão linear
        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)
        
        # Evitar divisão por zero
        if denominator == 0:
            return 0, y_mean, 0
        
        # Calcular slope (inclinação) e intercept (intercepto)
        slope = numerator / denominator
        intercept = y_mean - (slope * x_mean)
        
        # Calcular valores ajustados pela regressão
        y_pred = intercept + slope * x
        
        # Calcular o coeficiente de determinação (R²)
        ss_total = np.sum((y - y_mean) ** 2)
        ss_residual = np.sum((y - y_pred) ** 2)
        
        r_squared = 1 - (ss_residual / ss_total) if ss_total != 0 else 0
        
        return slope, intercept, r_squared
    
    # Inicializar arrays para armazenar os resultados
    linear_reg_values = np.zeros(len(df))
    linear_reg_values[:] = np.nan
    
    # Calcular a regressão linear para cada janela de período
    for i in range(period - 1, len(df)):
        # Definir os dados para a janela atual
        y = df[price_col].iloc[i-period+1:i+1].values
        x = np.arange(period)
        
        # Calcular a regressão linear
        slope, intercept, _ = calculate_linear_regression(x, y)
        
        # O valor da regressão linear para o ponto atual é o último ponto da linha ajustada
        linear_reg_values[i] = intercept + slope * (period - 1)
    
    # Converter para série pandas
    linear_reg = pd.Series(linear_reg_values, index=df.index)
    
    return linear_reg