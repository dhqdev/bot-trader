import pandas as pd
import numpy as np

def pivotPoints(data, pivot_type='standard'):
    """
    Calcula o indicador Pivot Points
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - pivot_type: Tipo de cálculo dos pivots ('standard', 'fibonacci', 'woodie', 'camarilla', 'demark')
    
    Retorno:
    pivot, s1, s2, s3, r1, r2, r3: Séries com os valores dos níveis de pivot
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
    
    # Verificar se 'open' está disponível para o método DeMark
    open_available = 'open' in data.columns or 'open'.lower() in data.columns
    open_col = 'open' if 'open' in data.columns else 'open'.lower() if 'open'.lower() in data.columns else None
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Adicionar informações sobre o período anterior
    df['prev_high'] = df[high_col].shift(1)
    df['prev_low'] = df[low_col].shift(1)
    df['prev_close'] = df[close_col].shift(1)
    if open_col:
        df['prev_open'] = df[open_col].shift(1)
    
    # Inicializar as séries para os níveis de pivot
    pivot = pd.Series(np.nan, index=df.index)
    s1 = pd.Series(np.nan, index=df.index)
    s2 = pd.Series(np.nan, index=df.index)
    s3 = pd.Series(np.nan, index=df.index)
    r1 = pd.Series(np.nan, index=df.index)
    r2 = pd.Series(np.nan, index=df.index)
    r3 = pd.Series(np.nan, index=df.index)
    
    # Calcular os Pivot Points de acordo com o método selecionado
    if pivot_type.lower() == 'standard':
        # Pivot Point (PP) = (High + Low + Close) / 3
        pivot = (df['prev_high'] + df['prev_low'] + df['prev_close']) / 3
        
        # Primeira resistência e suporte
        r1 = 2 * pivot - df['prev_low']
        s1 = 2 * pivot - df['prev_high']
        
        # Segunda resistência e suporte
        r2 = pivot + (df['prev_high'] - df['prev_low'])
        s2 = pivot - (df['prev_high'] - df['prev_low'])
        
        # Terceira resistência e suporte
        r3 = r1 + (df['prev_high'] - df['prev_low'])
        s3 = s1 - (df['prev_high'] - df['prev_low'])
    
    elif pivot_type.lower() == 'fibonacci':
        # Pivot Point é o mesmo do método padrão
        pivot = (df['prev_high'] + df['prev_low'] + df['prev_close']) / 3
        
        # Range do dia anterior
        range_hl = df['prev_high'] - df['prev_low']
        
        # Níveis Fibonacci para resistências
        r1 = pivot + 0.382 * range_hl
        r2 = pivot + 0.618 * range_hl
        r3 = pivot + 1.000 * range_hl
        
        # Níveis Fibonacci para suportes
        s1 = pivot - 0.382 * range_hl
        s2 = pivot - 0.618 * range_hl
        s3 = pivot - 1.000 * range_hl
    
    elif pivot_type.lower() == 'woodie':
        # Woodie dá mais peso ao preço de fechamento
        pivot = (df['prev_high'] + df['prev_low'] + 2 * df['prev_close']) / 4
        
        # Níveis de resistência e suporte
        r1 = 2 * pivot - df['prev_low']
        s1 = 2 * pivot - df['prev_high']
        
        r2 = pivot + (df['prev_high'] - df['prev_low'])
        s2 = pivot - (df['prev_high'] - df['prev_low'])
        
        r3 = pivot + 2 * (df['prev_high'] - df['prev_low'])
        s3 = pivot - 2 * (df['prev_high'] - df['prev_low'])
    
    elif pivot_type.lower() == 'camarilla':
        # Pivot Point é o mesmo do método padrão
        pivot = (df['prev_high'] + df['prev_low'] + df['prev_close']) / 3
        
        # Range do dia anterior
        range_hl = df['prev_high'] - df['prev_low']
        
        # Níveis Camarilla para resistências
        r1 = df['prev_close'] + range_hl * 1.1 / 12
        r2 = df['prev_close'] + range_hl * 1.1 / 6
        r3 = df['prev_close'] + range_hl * 1.1 / 4
        
        # Níveis Camarilla para suportes
        s1 = df['prev_close'] - range_hl * 1.1 / 12
        s2 = df['prev_close'] - range_hl * 1.1 / 6
        s3 = df['prev_close'] - range_hl * 1.1 / 4
    
    elif pivot_type.lower() == 'demark':
        if not open_col:
            raise ValueError("O método DeMark requer a coluna 'open'")
        
        # Condições para determinar o valor X
        x = pd.Series(np.nan, index=df.index)
        
        # Se Close > Open, X = 2 * High + Low + Close
        condition1 = df['prev_close'] > df['prev_open']
        x.loc[condition1] = 2 * df['prev_high'] + df['prev_low'] + df['prev_close']
        
        # Se Close < Open, X = High + 2 * Low + Close
        condition2 = df['prev_close'] < df['prev_open']
        x.loc[condition2] = df['prev_high'] + 2 * df['prev_low'] + df['prev_close']
        
        # Se Close = Open, X = High + Low + 2 * Close
        condition3 = df['prev_close'] == df['prev_open']
        x.loc[condition3] = df['prev_high'] + df['prev_low'] + 2 * df['prev_close']
        
        # Calcular o Pivot Point usando X
        pivot = x / 4
        
        # Resistência e suporte
        r1 = x / 2 - df['prev_low']
        s1 = x / 2 - df['prev_high']
        
        # DeMark tradicionalmente não tem R2, R3, S2, S3
        r2 = pd.Series(np.nan, index=df.index)
        r3 = pd.Series(np.nan, index=df.index)
        s2 = pd.Series(np.nan, index=df.index)
        s3 = pd.Series(np.nan, index=df.index)
    
    else:
        raise ValueError(f"Tipo de pivot '{pivot_type}' não reconhecido. Use 'standard', 'fibonacci', 'woodie', 'camarilla' ou 'demark'.")
    
    return pivot, s1, s2, s3, r1, r2, r3