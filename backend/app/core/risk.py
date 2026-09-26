"""Gerenciamento de risco da posição: tamanho, stop, alvos parciais,
break-even e trailing stop.

As mesmas funções são usadas pelo backtest (com máxima/mínima do candle)
e pelo motor ao vivo (com o preço atual), então o comportamento testado
é o comportamento executado.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Distância mínima de stop/trailing (%). Em candles curtos o ATR é minúsculo e o stop
# ficaria dentro do spread/slippage, saindo logo após a compra.
MIN_STOP_DISTANCE_PCT = 0.5


class TakeProfitLevel(BaseModel):
    pct: float = Field(gt=0, le=1000, description="Lucro (%) sobre o preço de entrada")
    size_pct: float = Field(gt=0, le=100, description="% da posição inicial vendida")


class RiskConfig(BaseModel):
    # tamanho da posição
    sizing_mode: Literal["fixed_quote", "percent_balance", "risk_percent"] = "fixed_quote"
    order_size_quote: float = Field(20.0, ge=0)
    balance_percent: float = Field(10.0, gt=0, le=100)
    risk_percent: float = Field(1.0, gt=0, le=10)
    max_position_quote: float = Field(0.0, ge=0, description="0 = sem limite")

    # stop inicial
    stop_loss_mode: Literal["none", "percent", "atr"] = "atr"
    stop_loss_pct: float = Field(3.0, gt=0, le=50)
    stop_loss_atr_mult: float = Field(3.0, gt=0, le=10)

    # alvos parciais
    # Padrões validados em backtest (7 pares x 1h/4h x 2 períodos): deixar a estratégia
    # decidir a saída, com stop largo por ATR, rendeu mais do que alvos curtos,
    # break-even cedo ou trailing apertado, que cortavam as tendências vencedoras.
    take_profits: list[TakeProfitLevel] = Field(default_factory=list)

    # proteção de lucro
    breakeven_at_pct: float = Field(0.0, ge=0, le=100, description="0 desativa")
    trailing_enabled: bool = False
    trailing_mode: Literal["percent", "atr"] = "atr"
    trailing_pct: float = Field(2.5, gt=0, le=50)
    trailing_atr_mult: float = Field(4.0, gt=0, le=10)
    trailing_activation_pct: float = Field(5.0, ge=0, le=100)

    # disciplina
    cooldown_bars: int = Field(1, ge=0, le=500)
    max_daily_loss_quote: float = Field(0.0, ge=0, description="0 desativa")
    fee_pct: float = Field(0.1, ge=0, le=2)

    @field_validator("take_profits")
    @classmethod
    def _sort_tps(cls, v: list[TakeProfitLevel]) -> list[TakeProfitLevel]:
        return sorted(v, key=lambda t: t.pct)[:5]


@dataclass
class PositionState:
    entry_price: float
    qty: float
    initial_qty: float
    highest: float
    stop: float | None
    stop_kind: str  # stop_loss | breakeven | trailing_stop
    tp_index: int
    atr: float | None
    trailing_active: bool = False


@dataclass
class ExitAction:
    reason: str  # stop_loss | breakeven | trailing_stop | take_profit
    fraction: float  # fração da quantidade restante (1 = tudo)
    price: float


def initial_stop(entry_price: float, atr_value: float | None, cfg: RiskConfig) -> float | None:
    if cfg.stop_loss_mode == "percent":
        return entry_price * (1 - cfg.stop_loss_pct / 100)
    if cfg.stop_loss_mode == "atr" and atr_value and atr_value > 0:
        stop = max(entry_price - cfg.stop_loss_atr_mult * atr_value, entry_price * 0.5)
        return min(stop, entry_price * (1 - MIN_STOP_DISTANCE_PCT / 100))
    if cfg.stop_loss_mode == "atr":  # sem ATR disponível, usa o percentual
        return entry_price * (1 - cfg.stop_loss_pct / 100)
    return None


def open_position(entry_price: float, qty: float, atr_value: float | None, cfg: RiskConfig) -> PositionState:
    return PositionState(
        entry_price=entry_price,
        qty=qty,
        initial_qty=qty,
        highest=entry_price,
        stop=initial_stop(entry_price, atr_value, cfg),
        stop_kind="stop_loss",
        tp_index=0,
        atr=atr_value,
    )


def position_size_quote(
    cfg: RiskConfig, available_quote: float, equity: float, entry_price: float, atr_value: float | None
) -> float:
    """Quanto da moeda de cotação (ex.: USDT) usar na compra."""
    if cfg.sizing_mode == "fixed_quote":
        size = cfg.order_size_quote
    elif cfg.sizing_mode == "percent_balance":
        size = available_quote * cfg.balance_percent / 100
    else:  # risk_percent: perde no máximo X% do patrimônio se o stop for atingido
        stop = initial_stop(entry_price, atr_value, cfg)
        if stop is None or stop >= entry_price:
            size = available_quote * cfg.balance_percent / 100
        else:
            stop_distance = (entry_price - stop) / entry_price
            size = equity * cfg.risk_percent / 100 / stop_distance
    if cfg.max_position_quote > 0:
        size = min(size, cfg.max_position_quote)
    return max(0.0, min(size, available_quote * 0.998))


def update(
    state: PositionState, cfg: RiskConfig, high: float, low: float, open_price: float | None = None
) -> list[ExitAction]:
    """Atualiza o estado com a nova faixa de preço e devolve as saídas a executar.

    Ao vivo: high = low = preço atual e open_price = None.
    No backtest: máxima/mínima/abertura do candle. Se o stop e um alvo forem
    tocados no mesmo candle, assume o pior caso (stop primeiro).
    """
    actions: list[ExitAction] = []

    live = open_price is None

    # 1) stop vigente (definido antes deste preço)
    if state.stop is not None and low <= state.stop:
        # ao vivo vende no preço atual; no backtest, no stop (ou na abertura, se abriu com gap abaixo)
        fill = low if live else min(state.stop, open_price)
        actions.append(ExitAction(state.stop_kind, 1.0, fill))
        return actions

    # 2) nova máxima
    if high > state.highest:
        state.highest = high
    best_gain_pct = (state.highest / state.entry_price - 1) * 100
    fee = cfg.fee_pct / 100

    # 3) break-even: protege a entrada (com as taxas) após X% de lucro
    if cfg.breakeven_at_pct > 0 and best_gain_pct >= cfg.breakeven_at_pct:
        be = state.entry_price * (1 + 2 * fee)
        if state.stop is None or be > state.stop:
            state.stop, state.stop_kind = be, "breakeven"

    # 4) trailing stop, ativado após X% de lucro
    if cfg.trailing_enabled and best_gain_pct >= cfg.trailing_activation_pct:
        state.trailing_active = True
    if state.trailing_active:
        if cfg.trailing_mode == "atr" and state.atr:
            distance = cfg.trailing_atr_mult * state.atr
        else:
            distance = state.highest * cfg.trailing_pct / 100
        trail = state.highest - max(distance, state.highest * MIN_STOP_DISTANCE_PCT / 100)
        if state.stop is None or trail > state.stop:
            state.stop, state.stop_kind = trail, "trailing_stop"

    # 5) alvos parciais (percentual da posição inicial). As frações são relativas
    # ao que resta, pois quem chama aplica as saídas em sequência.
    remaining = state.qty
    while state.tp_index < len(cfg.take_profits) and remaining > 0:
        level = cfg.take_profits[state.tp_index]
        target = state.entry_price * (1 + level.pct / 100)
        if high < target:
            break
        fill = high if live else max(target, open_price)
        to_sell = state.initial_qty * level.size_pct / 100
        if to_sell >= remaining * 0.999:
            fraction, remaining = 1.0, 0.0
        else:
            fraction, remaining = to_sell / remaining, remaining - to_sell
        actions.append(ExitAction("take_profit", fraction, fill))
        state.tp_index += 1
    return actions
