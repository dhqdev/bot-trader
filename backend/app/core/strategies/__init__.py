from app.core.strategies.base import Param, Strategy, StrategyOutput
from app.core.strategies.library import (
    ConfluenceStrategy,
    DonchianBreakoutStrategy,
    HiLoRsiStrategy,
    IgnitionStrategy,
    RsiBounceStrategy,
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
    RsiBounceStrategy(),  # nível rápido (experimental)
]

STRATEGIES: dict[str, Strategy] = {s.key: s for s in _ALL}
DEFAULT_STRATEGY = "squeeze"
DEFAULT_INTERVAL = "4h"  # em 1h quase todas perdem para o ruído e as taxas

# estratégias removidas por desempenho fraco -> substituta usada nos bots antigos
REMOVED = {"supertrend": "confluence", "ema_cross": "confluence", "macd_momentum": "confluence", "bb_reversion": "squeeze"}


# padrões antigos que ficaram mais soltos (v2.7.0): {estratégia: {parâmetro: valor antigo}}. Os bots que
# ainda usam o valor antigo (ou não têm o parâmetro, que é novo) passam para o novo na inicialização
# (engine.migrate_strategy_defaults). Mudou a lista? Suba DEFAULTS_VERSION.
PREVIOUS_DEFAULTS: dict[str, dict] = {
    "squeeze": {"min_squeeze": 8, "fresh_bars": 3},
    "ignition": {"vol_mult": 1.5},
    "vol_momentum": {"fresh_bars": 0},  # antes só comprava no candle em que a força cruzava o mínimo
    "confluence": {"fresh_bars": 10},
    "donchian_breakout": {"volume_mult": 1.2, "adx_min": 18},
}
DEFAULTS_VERSION = 1


def get_strategy(key: str) -> Strategy:
    try:
        return STRATEGIES[REMOVED.get(key, key)]
    except KeyError as exc:
        raise ValueError(f"Estratégia desconhecida: {key}") from exc


__all__ = [
    "STRATEGIES", "DEFAULT_STRATEGY", "DEFAULT_INTERVAL", "REMOVED", "PREVIOUS_DEFAULTS", "DEFAULTS_VERSION",
    "get_strategy", "Param", "Strategy", "StrategyOutput",
]  # fmt: skip
