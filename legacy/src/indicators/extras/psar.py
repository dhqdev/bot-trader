import pandas as pd
import numpy as np

def psar(data, af_start=0.02, af_increment=0.02, af_max=0.2):
    """
    Calcula o indicador PSAR (Parabolic Stop and Reverse)
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - af_start: Fator de aceleração inicial (padrão=0.02)
    - af_increment: Incremento do fator de aceleração (padrão=0.02)
    - af_max: Fator de aceleração máximo (padrão=0.2)
    
    Retorno:
    psar: Série com os valores do Parabolic SAR
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Inicializar as séries para PSAR
    psar_values = np.zeros(len(df))
    psar_values[:] = np.nan
    trend = np.zeros(len(df))  # 1 para tendência de alta, -1 para tendência de baixa
    af = np.zeros(len(df))  # Fator de aceleração
    ep = np.zeros(len(df))  # Extreme point
    
    # Verificar se temos dados suficientes
    if len(df) < 2:
        return pd.Series(psar_values, index=df.index)
    
    # Determinar tendência inicial
    if df[close_col].iloc[1] > df[close_col].iloc[0]:
        trend[1] = 1  # Tendência de alta
        psar_values[1] = df[low_col].iloc[0]  # PSAR inicial abaixo do primeiro low
        ep[1] = df[high_col].iloc[1]  # Primeiro EP é o high atual
    else:
        trend[1] = -1  # Tendência de baixa
        psar_values[1] = df[high_col].iloc[0]  # PSAR inicial acima do primeiro high
        ep[1] = df[low_col].iloc[1]  # Primeiro EP é o low atual
    
    af[1] = af_start
    
    # Calcular o PSAR para o restante dos dados
    for i in range(2, len(df)):
        # O PSAR é calculado com base nos valores anteriores
        psar_values[i] = psar_values[i-1] + af[i-1] * (ep[i-1] - psar_values[i-1])
        
        # Verificar se há reversão da tendência
        if trend[i-1] == 1:  # Tendência anterior de alta
            # Limitar o PSAR pelos mínimos anteriores
            psar_values[i] = min(psar_values[i], df[low_col].iloc[i-2], df[low_col].iloc[i-1])
            
            # Verificar se o PSAR é ultrapassado (tendência invertida)
            if psar_values[i] > df[low_col].iloc[i]:
                # Reversão para tendência de baixa
                trend[i] = -1
                psar_values[i] = max(df[high_col].iloc[i-2], df[high_col].iloc[i-1], df[high_col].iloc[i])
                ep[i] = df[low_col].iloc[i]
                af[i] = af_start
            else:
                # Continuação da tendência de alta
                trend[i] = 1
                
                # Atualizar EP se tivermos um novo máximo
                if df[high_col].iloc[i] > ep[i-1]:
                    ep[i] = df[high_col].iloc[i]
                    af[i] = min(af[i-1] + af_increment, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
        else:  # Tendência anterior de baixa
            # Limitar o PSAR pelos máximos anteriores
            psar_values[i] = max(psar_values[i], df[high_col].iloc[i-2], df[high_col].iloc[i-1])
            
            # Verificar se o PSAR é ultrapassado (tendência invertida)
            if psar_values[i] < df[high_col].iloc[i]:
                # Reversão para tendência de alta
                trend[i] = 1
                psar_values[i] = min(df[low_col].iloc[i-2], df[low_col].iloc[i-1], df[low_col].iloc[i])
                ep[i] = df[high_col].iloc[i]
                af[i] = af_start
            else:
                # Continuação da tendência de baixa
                trend[i] = -1
                
                # Atualizar EP se tivermos um novo mínimo
                if df[low_col].iloc[i] < ep[i-1]:
                    ep[i] = df[low_col].iloc[i]
                    af[i] = min(af[i-1] + af_increment, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
    
    return pd.Series(psar_values, index=df.index)