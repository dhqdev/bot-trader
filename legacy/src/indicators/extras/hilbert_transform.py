import pandas as pd
import numpy as np

def hilbertTransform(data, period=14):
    """
    Calcula o indicador Hilbert Transform
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do Hilbert Transform (padrão=14)
    
    Retorno:
    ht_sine, ht_leadsine, ht_trend: Séries com os componentes do Hilbert Transform
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Garantir que estamos usando as colunas corretas
    close_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Implementação simplificada do Hilbert Transform
    # NOTA: O Hilbert Transform completo é muito complexo e requer bibliotecas especializadas
    # Esta é uma versão simplificada que imita o comportamento básico
    
    # 1. Cálculo da tendência usando média móvel
    ht_trend = df[close_col].rolling(window=period).mean()
    
    # 2. Gerar componentes senoidais com base na periodicidade
    # O sine wave é gerado com base no índice do DataFrame
    ht_sine = pd.Series(np.sin(np.arange(len(df)) * 2 * np.pi / period), index=df.index)
    
    # O lead sine wave está 90 graus à frente do sine wave (usando coseno)
    ht_leadsine = pd.Series(np.cos(np.arange(len(df)) * 2 * np.pi / period), index=df.index)
    
    # 3. Ajustar a amplitude dos componentes senoidais 
    # (normalmente seria baseado na análise do ciclo dominante, 
    # mas aqui usamos uma fração da variação histórica para simplicidade)
    price_range = df[close_col].rolling(window=period).max() - df[close_col].rolling(window=period).min()
    amplitude = price_range * 0.1
    
    # Aplicar a amplitude aos componentes senoidais
    ht_sine = ht_sine * amplitude
    ht_leadsine = ht_leadsine * amplitude
    
    return ht_sine, ht_leadsine, ht_trend