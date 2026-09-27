"""Tipos comuns da execução: intervalos, regras do par, ordens executadas e simulação.

A corretora do sistema é a OKX (core/okx.py). Este módulo não depende de corretora:
o motor, o backtest e o modo simulado usam só estes tipos.
"""

import math
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

# tempos de candle aceitos (todos existem na OKX)
INTERVAL_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440,
}  # fmt: skip

KLINE_COLUMNS = ["time", "open", "high", "low", "close", "volume", "close_time"]


def interval_ms(interval: str) -> int:
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Intervalo inválido: {interval}")
    return INTERVAL_MINUTES[interval] * 60_000


def now_ms() -> int:
    return int(time.time() * 1000)


def _decimals(step: float) -> int:
    if step <= 0 or step >= 1:
        return 0
    return max(0, -int(math.floor(math.log10(step) + 1e-9)))


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    d_step = Decimal(str(step))
    return float((Decimal(str(value)) / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step)


@dataclass
class SymbolRules:
    symbol: str
    base: str
    quote: str
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float
    quote_precision: int = 8

    def floor_qty(self, qty: float) -> float:
        return _floor_to_step(qty, self.step_size)

    def format_qty(self, qty: float) -> str:
        return f"{self.floor_qty(qty):.{_decimals(self.step_size)}f}"

    def format_quote(self, amount: float) -> str:
        decimals = min(self.quote_precision, 8)
        return f"{_floor_to_step(amount, 10 ** -decimals):.{decimals}f}"

    def is_tradeable(self, qty: float, price: float) -> bool:
        q = self.floor_qty(qty)
        return q >= self.min_qty and q > 0 and q * price >= self.min_notional


@dataclass
class Fill:
    side: str
    order_id: str
    status: str
    qty: float  # quantidade executada (bruta)
    net_qty: float  # quantidade recebida após taxa cobrada no ativo base
    quote: float  # valor bruto em moeda de cotação
    avg_price: float
    fee_quote: float  # taxa convertida para a moeda de cotação
    net_quote: float  # compra: custo total | venda: valor líquido recebido
    raw: dict = field(default_factory=dict)


class PaperTrader:
    """Execução simulada com preço real, taxa e slippage."""

    mode = "paper"

    def __init__(self, market, fee_pct: float = 0.1, slippage_pct: float = 0.05):
        self.market = market
        self.fee = fee_pct / 100
        self.slippage = slippage_pct / 100

    def market_buy_quote(self, symbol: str, quote_amount: float, rules: SymbolRules) -> Fill:
        price = self.market.price(symbol) * (1 + self.slippage)
        qty = rules.floor_qty(quote_amount / (price * (1 + self.fee)))
        gross = qty * price
        fee = gross * self.fee
        return Fill("BUY", f"paper-{now_ms()}", "FILLED", qty, qty, gross, price, fee, gross + fee)

    def market_sell_qty(self, symbol: str, qty: float, rules: SymbolRules) -> Fill:
        price = self.market.price(symbol) * (1 - self.slippage)
        qty = rules.floor_qty(qty)
        gross = qty * price
        fee = gross * self.fee
        return Fill("SELL", f"paper-{now_ms()}", "FILLED", qty, qty, gross, price, fee, gross - fee)
