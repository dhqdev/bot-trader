from app.core.strategies.base import Param, Strategy, StrategyOutput
from app.core.strategies.library import (
    ConfluenceStrategy,
    DonchianBreakoutStrategy,
    HiLoRsiStrategy,
    IgnitionStrategy,
    SqueezeBreakoutStrategy,
    VolMomentumStrategy,
)

# ordem = ranking nos testes (a primeira é a recomendada)
_ALL: list[Strategy] = [
    SqueezeBreakoutStrategy(),
    IgnitionStrategy(),
    VolMomentumStrategy(),
    ConfluenceStrategy(),
    DonchianBreakoutStrategy(),
    HiLoRsiStrategy(),
]

STRATEGIES: dict[str, Strategy] = {s.key: s for s in _ALL}
DEFAULT_STRATEGY = "squeeze"
DEFAULT_INTERVAL = "4h"  # em 1h quase todas perdem para o ruído e as taxas

# estratégias removidas por desempenho fraco -> substituta usada nos bots antigos
REMOVED = {"supertrend": "confluence", "ema_cross": "confluence", "macd_momentum": "confluence", "bb_reversion": "squeeze"}


def get_strategy(key: str) -> Strategy:
    try:
        return STRATEGIES[REMOVED.get(key, key)]
    except KeyError as exc:
        raise ValueError(f"Estratégia desconhecida: {key}") from exc


__all__ = ["STRATEGIES", "DEFAULT_STRATEGY", "DEFAULT_INTERVAL", "REMOVED", "get_strategy", "Param", "Strategy", "StrategyOutput"]
