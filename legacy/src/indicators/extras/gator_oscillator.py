import pandas as pd
import numpy as np

def gatorOscillator(data, jaw_period=13, jaw_offset=8, teeth_period=8, teeth_offset=5, lips_period=5, lips_offset=3):
    """
    Calcula o indicador Gator Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - jaw_period: Período para cálculo da linha Jaw (mandíbula do Alligator) (padrão=13)
    - jaw_offset: Deslocamento para a linha Jaw (padrão=8)
    - teeth_period: Período para cálculo da linha Teeth (dentes do Alligator) (padrão=8)
    - teeth_offset: Deslocamento para a linha Teeth (padrão=5)
    - lips_period: Período para cálculo da linha Lips (lábios do Alligator) (padrão=5)
    - lips_offset: Deslocamento para a linha Lips (padrão=3)
    
    Retorno:
    jaw_teeth, teeth_lips: Séries com os valores do Gator Oscillator
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
    
    # Calcular SMMAs para as linhas do Alligator
    jaw_smma = calculate_smma(df['median_price'].values, jaw_period)
    teeth_smma = calculate_smma(df['median_price'].values, teeth_period)
    lips_smma = calculate_smma(df['median_price'].values, lips_period)
    
    # Criar as colunas do Alligator
    df['jaw'] = pd.Series(jaw_smma, index=df.index)
    df['teeth'] = pd.Series(teeth_smma, index=df.index)
    df['lips'] = pd.Series(lips_smma, index=df.index)
    
    # Aplicar os deslocamentos (shift)
    # Valores negativos porque estamos deslocando para o futuro
    df['jaw_shifted'] = df['jaw'].shift(-jaw_offset)
    df['teeth_shifted'] = df['teeth'].shift(-teeth_offset)
    df['lips_shifted'] = df['lips'].shift(-lips_offset)
    
    # Calcular o Gator Oscillator
    # Parte superior (jaw_teeth): valor absoluto da diferença entre Jaw e Teeth
    jaw_teeth = abs(df['jaw_shifted'] - df['teeth_shifted'])
    
    # Parte inferior (teeth_lips): valor negativo do valor absoluto da diferença entre Teeth e Lips
    teeth_lips = -abs(df['teeth_shifted'] - df['lips_shifted'])
    
    return jaw_teeth, teeth_lips