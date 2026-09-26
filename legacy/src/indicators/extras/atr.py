import pandas as pd
import numpy as np


def atr(data, period=14):
    """
    Calcula o indicador ATR (Average True Range)

    Parâmetros:
    - data: DataFrame contendo os dados de preço
    - period: Período para cálculo do ATR (padrão=14)

    Retorno:
    atr: Série com os valores do Average True Range
    """
    # Verificar se as colunas necessárias existem
    required_cols = ["high", "low", "close"]
    for col in required_cols:
        if col not in data.columns and col.lower() not in data.columns:
            raise ValueError(f"Coluna '{col}' não encontrada nos dados")

    # Garantir que estamos usando as colunas corretas
    high_col = "high" if "high" in data.columns else "high".lower()
    low_col = "low" if "low" in data.columns else "low".lower()
    close_col = "close" if "close" in data.columns else "close".lower()

    # Criar uma cópia para evitar modificar o DataFrame original
    df = data.copy()

    # Calcular o True Range (TR)
    # TR = max(high - low, |high - close_prev|, |low - close_prev|)
    df["prev_close"] = df[close_col].shift(1)

    # Calculando os três componentes do True Range
    df["high_low"] = df[high_col] - df[low_col]
    df["high_prev_close"] = np.abs(df[high_col] - df["prev_close"])
    df["low_prev_close"] = np.abs(df[low_col] - df["prev_close"])

    # Para o primeiro valor, não temos o preço de fechamento anterior
    df.loc[df.index[0], "high_prev_close"] = np.nan
    df.loc[df.index[0], "low_prev_close"] = np.nan

    # True Range é o máximo dos três componentes
    df["tr"] = df[["high_low", "high_prev_close", "low_prev_close"]].max(axis=1)

    # Para o primeiro valor, TR é simplesmente high - low
    df.loc[df.index[0], "tr"] = df.loc[df.index[0], "high_low"]

    # Calcular o ATR como média móvel do TR
    atr_values = df["tr"].rolling(window=period).mean()

    # Para valores iniciais onde não temos período completo, calcular média simples
    for i in range(1, min(period, len(df))):
        atr_values.iloc[i] = df["tr"].iloc[: i + 1].mean()

    return atr_values
