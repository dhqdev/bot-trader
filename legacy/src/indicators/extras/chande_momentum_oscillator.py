import pandas as pd
import numpy as np

def chandeMomentumOscillator(data, period=14, use_close=True):
    """
    Calcula o indicador Chande Momentum Oscillator
    
    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do CMO (padrão=14)
    - use_close: Se True, utiliza o preço de fechamento; caso contrário, utiliza a abertura
    
    Retorno:
    cmo: Série com os valores do Chande Momentum Oscillator
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # Determinar qual coluna de preço usar
    price_col = 'close' if use_close else 'open'
    if price_col not in data.columns:
        price_col = price_col.lower()
        if price_col not in data.columns and price_col == 'open':
            # Caso 'open' não esteja disponível, usar 'close'
            price_col = 'close' if 'close' in data.columns else 'close'.lower()
    
    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()
    
    # Calcular variação diária
    df['price_change'] = df[price_col].diff()
    
    # Separar as variações positivas e negativas
    df['gain'] = np.where(df['price_change'] > 0, df['price_change'], 0)
    df['loss'] = np.where(df['price_change'] < 0, -df['price_change'], 0)
    
    # Calcular a soma das variações positivas e negativas para o período
    df['sum_gains'] = df['gain'].rolling(window=period).sum()
    df['sum_losses'] = df['loss'].rolling(window=period).sum()
    
    # Calcular o CMO: 100 * ((sum_gains - sum_losses) / (sum_gains + sum_losses))
    cmo = 100 * ((df['sum_gains'] - df['sum_losses']) / 
                 (df['sum_gains'] + df['sum_losses']))
    
    # Preencher valores NaN ou infinitos
    cmo = cmo.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    return cmo