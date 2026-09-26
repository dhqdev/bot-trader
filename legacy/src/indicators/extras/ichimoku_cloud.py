import pandas as pd
import numpy as np

def ichimokuCloud(data, tenkan_period=9, kijun_period=26, senkou_span_b_period=52, displacement=26):
    """
    Calcula o indicador Ichimoku Cloud
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - tenkan_period: Período para o Tenkan-sen (Linha de Conversão) (padrão=9)
    - kijun_period: Período para o Kijun-sen (Linha Base) (padrão=26)
    - senkou_span_b_period: Período para o Senkou Span B (Segunda linha da nuvem) (padrão=52)
    - displacement: Período de deslocamento para o Senkou Span (Nuvem) (padrão=26)
    
    Retorno:
    tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span: Séries com os componentes do Ichimoku Cloud
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
    
    # Função para calcular o meio do alcance (min/max) para um período
    def donchian(high, low, period):
        return (high.rolling(window=period).max() + low.rolling(window=period).min()) / 2
    
    # Cálculo do Tenkan-sen (Linha de Conversão)
    tenkan_sen = donchian(df[high_col], df[low_col], tenkan_period)
    
    # Cálculo do Kijun-sen (Linha Base)
    kijun_sen = donchian(df[high_col], df[low_col], kijun_period)
    
    # Cálculo do Senkou Span A (Primeira linha da nuvem)
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
    
    # Cálculo do Senkou Span B (Segunda linha da nuvem)
    senkou_span_b = donchian(df[high_col], df[low_col], senkou_span_b_period).shift(displacement)
    
    # Cálculo do Chikou Span (Linha de Atraso)
    chikou_span = df[close_col].shift(-displacement)
    
    return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span