from app.core.strategies.base import Param, Strategy, StrategyOutput
from app.core.strategies.library import (
    BollingerReversionStrategy,
    ConfluenceStrategy,
    DonchianBreakoutStrategy,
    EmaCrossStrategy,
    HiLoRsiStrategy,
    MacdMomentumStrategy,
    SupertrendStrategy,
)

_ALL: list[Strategy] = [
    ConfluenceStrategy(),
    HiLoRsiStrategy(),
    SupertrendStrategy(),
    EmaCrossStrategy(),
    DonchianBreakoutStrategy(),
    MacdMomentumStrategy(),
    BollingerReversionStrategy(),
]

STRATEGIES: dict[str, Strategy] = {s.key: s for s in _ALL}
DEFAULT_STRATEGY = "confluence"


def get_strategy(key: str) -> Strategy:
    try:
        return STRATEGIES[key]
    except KeyError as exc:
        raise ValueError(f"Estratégia desconhecida: {key}") from exc


__all__ = ["STRATEGIES", "DEFAULT_STRATEGY", "get_strategy", "Param", "Strategy", "StrategyOutput"]
