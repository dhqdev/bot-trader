import pandas as pd
import numpy as np

def aroonOscillator(data, period=14):
    """
    Calcula o indicador Aroon Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Aroon (padrão=14)
    
    Retorno:
    aroon_oscillator: Série com os valores do Aroon Oscillator
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Função para calcular índices dos máximos/mínimos em um período
    def rolling_argmax_min(series, window, find_max=True):
        result = np.zeros(len(series))
        result[:] = np.nan
        
        for i in range(window - 1, len(series)):
            if find_max:
                idx = series.iloc[i - window + 1:i + 1].idxmax()
            else:
                idx = series.iloc[i - window + 1:i + 1].idxmin()
            
            # Converter para dias desde o extremo (0 = hoje, window-1 = mais antigo)
            loc_in_df = series.index.get_loc(idx)
            loc_in_window = loc_in_df - (i - window + 1)
            days_since = window - 1 - loc_in_window
            
            result[i] = days_since
            
        return pd.Series(result, index=series.index)
    
    # Calcular períodos desde o máximo e mínimo
    days_since_high = rolling_argmax_min(df[high_col], period, find_max=True)
    days_since_low = rolling_argmax_min(df[low_col], period, find_max=False)
    
    # Calcular Aroon Up e Aroon Down
    aroon_up = 100 * (period - days_since_high) / period
    aroon_down = 100 * (period - days_since_low) / period
    
    # Calcular Aroon Oscillator
    aroon_oscillator = aroon_up - aroon_down
    
    return aroon_oscillator