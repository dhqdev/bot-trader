import pandas as pd
import numpy as np

def acceleratorOscillator(data, sma_period=5, ao_period_fast=5, ao_period_slow=34):
    """
    Calcula o indicador Accelerator Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - sma_period: Período para suavização do Awesome Oscillator (padrão=5)
    - ao_period_fast: Período rápido para o Awesome Oscillator (padrão=5)
    - ao_period_slow: Período lento para o Awesome Oscillator (padrão=34)
    
    Retorno:
    accelerator_oscillator: Série com os valores do Accelerator Oscillator
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
    
    # Calcular o preço médio (midpoint)
    df['midpoint'] = (df[high_col] + df[low_col]) / 2
    
    # Calcular as médias móveis do midpoint
    df['ao_fast'] = df['midpoint'].rolling(window=ao_period_fast).mean()
    df['ao_slow'] = df['midpoint'].rolling(window=ao_period_slow).mean()
    
    # Calcular o Awesome Oscillator (AO)
    df['awesome_oscillator'] = df['ao_fast'] - df['ao_slow']
    
    # Calcular o SMA do Awesome Oscillator
    df['ao_sma'] = df['awesome_oscillator'].rolling(window=sma_period).mean()
    
    # Calcular o Accelerator Oscillator (AC = AO - SMA(AO))
    accelerator_oscillator = df['awesome_oscillator'] - df['ao_sma']
    
    return accelerator_oscillator