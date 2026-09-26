import pandas as pd
import numpy as np

def williamsAlligator(data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3):
    """
    Calcula o indicador Williams Alligator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - jaw_period: Período para cálculo da linha Jaw (mandíbula do Alligator) (padrão=13)
    - jaw_offset: Deslocamento para a linha Jaw (padrão=8)
    - teeth_period: Período para cálculo da linha Teeth (dentes do Alligator) (padrão=8)
    - teeth_offset: Deslocamento para a linha Teeth (padrão=5)
    - lips_period: Período para cálculo da linha Lips (lábios do Alligator) (padrão=5)
    - lips_offset: Deslocamento para a linha Lips (padrão=3)
    
    Retorno:
    jaw, teeth, lips: Séries com os valores dos componentes do Williams Alligator
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    high_col = 'high' if 'high' in data.columns else 'high'.lower()
    low_col = 'low' if 'low' in data.columns else 'low'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular o preço médio
    df['median_price'] = (df[high_col] + df[low_col]) / 2
    
    # Implementar SMMA (Smoothed Moving Average)
    def calculate_smma(data, period):
        smma = np.zeros_like(data)
        smma[:period] = np.nan
        
        # Inicializar com a média dos primeiros 'period' elementos
        smma[period - 1] = np.mean(data[:period])
        
        # Calcular o SMMA para os elementos restantes
        for i in range(period, len(data)):
            smma[i] = (smma[i - 1] * (period - 1) + data[i]) / period
        
        return smma
    
    # Calcular SMMAs
    smma_jaw = calculate_smma(df['median_price'].values, jaw_period)
    smma_teeth = calculate_smma(df['median_price'].values, teeth_period)
    smma_lips = calculate_smma(df['median_price'].values, lips_period)
    
    # Criar as colunas do Alligator
    jaw = pd.Series(smma_jaw, index=df.index)
    teeth = pd.Series(smma_teeth, index=df.index)
    lips = pd.Series(smma_lips, index=df.index)
    
    # Aplicar os deslocamentos (shift)
    # Valores negativos porque estamos deslocando para o futuro
    jaw_shifted = jaw.shift(-jaw_offset)
    teeth_shifted = teeth.shift(-teeth_offset)
    lips_shifted = lips.shift(-lips_offset)
    
    return jaw_shifted, teeth_shifted, lips_shifted