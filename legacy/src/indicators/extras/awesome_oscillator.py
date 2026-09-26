import pandas as pd
import numpy as np

def awesomeOscillator(data, fast_period=5, slow_period=34):
    """
    Calcula o indicador Awesome Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - fast_period: Período para a média móvel rápida (padrão=5)
    - slow_period: Período para a média móvel lenta (padrão=34)
    
    Retorno:
    awesome_oscillator: Série com os valores do Awesome Oscillator
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
    
    # Calcular o ponto médio dos preços
    df['midpoint'] = (df[high_col] + df[low_col]) / 2
    
    # Calcular as médias móveis simples do ponto médio
    df['sma_fast'] = df['midpoint'].rolling(window=fast_period).mean()
    df['sma_slow'] = df['midpoint'].rolling(window=slow_period).mean()
    
    # Calcular o Awesome Oscillator
    awesome_oscillator = df['sma_fast'] - df['sma_slow']
    
    return awesome_oscillator