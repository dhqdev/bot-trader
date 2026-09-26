import numpy as np
import pandas as pd


def backtestRunner(
    stock_data: pd.DataFrame, strategy_function, strategy_instance=None, periods=900, initial_balance=1000, **strategy_kwargs
):
    """
    Executa um backtest de qualquer estratégia que segue a lógica de:
    - True = comprado
    - False = vendido

    O bot verifica se já está comprado/vendido e só age no primeiro sinal.
    """
    # 🔹 Ajuste para garantir que há dados suficientes para calcular médias móveis corretamente
    min_required_periods = strategy_kwargs.get("slow_window", 40) + 20  # buffer extra
    stock_data = stock_data[-max(periods, min_required_periods) :].copy().reset_index(drop=True)

    # 🔹 REMOVE LINHAS INICIAIS COM NaN PARA EVITAR PROBLEMAS
    stock_data.dropna(inplace=True)

    balance = initial_balance  # Saldo inicial
    position = 0  # 1 = comprado, 0 = fora
    entry_price = 0
    last_signal = None
    trades = 0

    print(f"📊 Iniciando backtest da estratégia: {strategy_function.__name__}")
    print(f"🔹 Balanço inicial: ${balance:.2f}")

    for i in range(1, len(stock_data)):
        current_data = stock_data.iloc[: i + 1]

        # Se a função precisa de 'self', passa também current_data + demais kwargs
        if strategy_instance:
            signal = strategy_function(strategy_instance, current_data, **strategy_kwargs)
        else:
            signal = strategy_function(current_data, **strategy_kwargs)

        if signal is None:
            continue

        close_price = stock_data.iloc[i]["close_price"]

        if signal and position == 0 and last_signal != "buy":
            position = 1
            entry_price = close_price
            last_signal = "buy"
            trades += 1

        elif not signal and position == 1 and last_signal != "sell":
            position = 0
            profit = ((close_price - entry_price) / entry_price) * balance
            balance += profit
            last_signal = "sell"
            trades += 1

    if position == 1:
        final_price = stock_data.iloc[-1]["close_price"]
        profit = ((final_price - entry_price) / entry_price) * balance
        balance += profit

    profit_percentage = ((balance - initial_balance) / initial_balance) * 100

    print(f"🔹 Balanço final: ${balance:.2f}")
    print(f"📈 Lucro/prejuízo percentual: {profit_percentage:.2f}%")
    print(f"📊 Total de operações realizadas: {trades}")

    return profit_percentage
