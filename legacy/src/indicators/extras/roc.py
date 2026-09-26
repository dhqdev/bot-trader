import pandas as pd
import numpy as np

def roc(data, period=12):
    """
    Calcula o indicador ROC
    
    Parâmetros:
    - data: Descrição do parâmetro
    - period: Descrição do parâmetro
    
    Retorno:
    roc: Série com os valores do Rate of Change
    """
    # Verificar se as colunas necessárias existem
    required_cols = ['high', 'low', 'close']
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")
    
    # TODO: Implementar o cálculo do indicador ROC
    
    # Código-base para iniciar a implementação
    
    return roc
