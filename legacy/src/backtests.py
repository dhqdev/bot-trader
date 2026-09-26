from binance.client import Client
from src.modules.BinanceTraderBot import BinanceTraderBot
from src.tests.backtestRunner import backtestRunner

import sys

# Reconfigura stdout para UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Imprime BOM para que editores como o Notepad entendam automaticamente como UTF-8
sys.stdout.write("\ufeff")


from src.strategies.moving_average_antecipation import getMovingAverageAntecipationTradeStrategy
from src.strategies.ut_bot_alerts import utBotAlerts

from src.strategies.moving_average import getMovingAverageTradeStrategy
from src.strategies.rsi_strategy import getRsiTradeStrategy
from src.strategies.vortex_strategy import getVortexTradeStrategy
from src.strategies.ma_rsi_volume_strategy import getMovingAverageRSIVolumeStrategy
from src.strategies.chilo import getChiloStrategy
import src.strategies.chilo_rsi as chilo_mod

# ------------------------------------------------------------------------
# 🔎 AJUSTES BACKTESTS 🔎

BASE_STOCK = "JUP"  # Código base da criptomoeda
QUOTE_STOCK = "USDT"  # Código da moeda cotada
INITIAL_BALANCE = 1000  # Valor de investimento inicial em USDT ou BRL

# ----------------------------------------
# 📊 PERÍODO DO CANDLE, SELECIONAR 1 📊

# CANDLE_PERIOD = Client.KLINE_INTERVAL_4HOUR
# CANDLE_PERIOD = Client.KLINE_INTERVAL_15MINUTE
CANDLE_PERIOD = Client.KLINE_INTERVAL_1HOUR
CLANDES_RODADOS = 24 * 90

# ------------------------------------------------------------------------
# ⏬ SELEÇÃO DE ESTRATÉGIAS ⏬

devTrader = BinanceTraderBot(
    base_stock=BASE_STOCK,
    quote_stock=QUOTE_STOCK,
    traded_quantity=0,
    traded_percentage=100,
    candle_period=CANDLE_PERIOD,
)
devTrader.updateAllData()


print(f"\n{BASE_STOCK} - CHILO RSI - {str(CANDLE_PERIOD)}")
chilo_mod.USE_IN_MEMORY_ONLY = True
backtestRunner(
    stock_data=devTrader.stock_data,
    strategy_function=chilo_mod.ChiloRSIStrategy,
    strategy_instance=devTrader,
    periods=CLANDES_RODADOS,
    initial_balance=INITIAL_BALANCE,
    backtest_verbose=False,
)
chilo_mod.USE_IN_MEMORY_ONLY = False


# print(f"\n{BASE_STOCK} - CHILO ORIGINAL - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getChiloStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     backtest_verbose=False,
#     length=34,
# )


# print(f"\n{BASE_STOCK} - UT BOTS - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=utBotAlerts,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     atr_multiplier=2,
#     atr_period=1,
#     backtest_verbose=False,
# )

# print(f"\n{BASE_STOCK} - MA RSI e VOLUME - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getMovingAverageRSIVolumeStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     backtest_verbose=False,
# )


# print(f"\n{BASE_STOCK} - MA ANTECIPATION - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getMovingAverageAntecipationTradeStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     volatility_factor=0.5,
#     fast_window=7,
#     slow_window=40,
#     backtest_verbose=False,
# )


# print(f"\n{BASE_STOCK} - MA SIMPLES FALLBACK - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getMovingAverageTradeStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     fast_window=7,
#     slow_window=40,
#     backtest_verbose=False,
# )

# print(f"\n{BASE_STOCK} - RSI - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getRsiTradeStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     low=30,
#     high=70,
#     backtest_verbose=False,
# )

# print(f"\n{BASE_STOCK} - VORTEX - {str(CANDLE_PERIOD)}")
# backtestRunner(
#     stock_data=devTrader.stock_data,
#     strategy_function=getVortexTradeStrategy,
#     periods=CLANDES_RODADOS,
#     initial_balance=INITIAL_BALANCE,
#     backtest_verbose=False,
# )


print("\n\n")
