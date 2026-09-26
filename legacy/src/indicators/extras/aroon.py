import pandas as pd
import numpy as np

def aroon(data, period=14):
    """
    Calcula o indicador Aroon
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Aroon (padrão=14)
    
    Retorno:
    aroon_up, aroon_down, aroon_oscillator: Séries com os valores do Aroon Up, Aroon Down e Aroon Oscillator
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
    
    # Calcular os períodos desde o máximo/mínimo de alta/baixa
    # Função para calcular índices dos máximos/mínimos em um período
    def calculate_periods_since_extreme(df, period, high_low_col, find_max=True):
        result = []
        
        for i in range(len(df)):
            if i < period - 1:
                result.append(np.nan)
                continue
                
            # Extrair a janela para o período
            window = df[high_low_col].iloc[i - period + 1 : i + 1]
            
            # Encontrar o índice do máximo ou mínimo relativo ao início da janela
            if find_max:
                idx = window.idxmax()
            else:
                idx = window.idxmin()
            
            # Converter para posição na janela
            pos = df.index.get_loc(idx) - (i - period + 1)
            
            # Calcular períodos desde o extremo
            periods_since = period - 1 - pos
            
            result.append(periods_since)
        
        return result
    
    # Calcular períodos desde o máximo e mínimo
    periods_since_high = calculate_periods_since_extreme(df, period, high_col, find_max=True)
    periods_since_low = calculate_periods_since_extreme(df, period, low_col, find_max=False)
    
    # Calcular Aroon Up e Aroon Down
    aroon_up = pd.Series([(period - p) / period * 100 if not np.isnan(p) else np.nan for p in periods_since_high], 
                        index=df.index)
    aroon_down = pd.Series([(period - p) / period * 100 if not np.isnan(p) else np.nan for p in periods_since_low], 
                          index=df.index)
    
    # Calcular Aroon Oscillator
    aroon_oscillator = aroon_up - aroon_down
    
    return aroon_up, aroon_down, aroon_oscillator