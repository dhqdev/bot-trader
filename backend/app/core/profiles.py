"""Perfis prontos em 3 níveis: Rápido (minutos), Médio (horas) e Lento (dias).

Cada perfil é uma combinação de estratégia + tempo de candle + regras de risco
+ filtro de sentimento. Os números foram medidos em backtest (set/2026) com o
código de produção, dados reais da Binance em 14 pares (BTC, ETH, SOL, BNB,
XRP, LINK, ADA, DOGE, AVAX, DOT, LTC, TRX, NEAR, JUP), taxa de 0,1% e slippage
de 0,05% por ordem, com 100% do capital em cada operação e o Índice de Medo e
Ganância real de cada dia. Resultado passado não garante o futuro.

Filtro de sentimento de cada perfil (o que rendeu mais nos dois grupos de pares):
- Ignição 1h e os rápidos: só compra com o índice subindo na semana
  (Ignição 1h: +2,7% -> +8,3% na mediana, queda média -19,8% -> -15,9%);
- HiLo 2h, Squeeze 4h e Confluência 1d: evita comprar com medo extremo
  (Squeeze 4h: +20,9% -> +23,3%; HiLo 2h: +0,7% -> +4,3%; Confluência: igual).
"""

from app.core.risk import RiskConfig
from app.core.strategies import STRATEGIES

FAST_RISK = {
    "stop_loss_mode": "atr", "stop_loss_atr_mult": 1.5,
    "take_profits": [{"pct": 1.0, "size_pct": 50}], "breakeven_at_pct": 0,
    "trailing_enabled": True, "trailing_mode": "atr", "trailing_atr_mult": 2.0, "trailing_activation_pct": 1.0,
    "cooldown_bars": 3, "sentiment_filter": "rising",
}  # fmt: skip
MEDIUM_RISK = {
    "stop_loss_mode": "atr", "stop_loss_atr_mult": 2.0, "take_profits": [], "breakeven_at_pct": 0,
    "trailing_enabled": True, "trailing_mode": "atr", "trailing_atr_mult": 3.0, "trailing_activation_pct": 2.0,
    "cooldown_bars": 2, "sentiment_filter": "avoid_extreme_fear",
}  # fmt: skip
SLOW_RISK = {
    "stop_loss_mode": "atr", "stop_loss_atr_mult": 3.0, "take_profits": [], "breakeven_at_pct": 0,
    "trailing_enabled": False, "cooldown_bars": 1, "sentiment_filter": "avoid_extreme_fear",
}  # fmt: skip
# Ignição 1h usa o risco lento, mas com o filtro "sentimento subindo" (o melhor para ela)
RISING_SLOW_RISK = {**SLOW_RISK, "sentiment_filter": "rising"}

TIERS = [
    {
        "key": "rapido",
        "name": "Rápido",
        "risk": "Alto",
        "holding": "minutos",
        "timeframes": "5 e 15 minutos",
        "description": "Operações de minutos, várias por dia, em candles de 5 e 15 minutos.",
        "warning": (
            "Experimental. Nos testes, todas as estratégias de minutos perderam dinheiro depois das taxas: "
            "cada operação custa cerca de 0,3% entre taxa e slippage, mais do que costumam render movimentos "
            "tão curtos. Pagar a taxa com BNB reduz a perda, mas não a elimina. Use no modo simulado."
        ),
    },
    {
        "key": "medio",
        "name": "Médio",
        "risk": "Médio",
        "holding": "horas",
        "timeframes": "1 e 2 horas",
        "description": "Operações de algumas horas a 1 ou 2 dias, em candles de 1 e 2 horas. Resultado moderado, com boa proteção nas quedas.",
        "warning": None,
    },
    {
        "key": "lento",
        "name": "Lento",
        "risk": "Baixo",
        "holding": "dias",
        "timeframes": "4 horas e 1 dia",
        "description": (
            "Operações de dias a semanas, em candles de 4 horas e diários. Melhor resultado e maior chance de lucro "
            "nos testes; em compensação, as oscilações no caminho podem ser maiores."
        ),
        "warning": None,
    },
]

PROFILES = [
    {
        "key": "rapido_repique_5m",
        "tier": "rapido",
        "name": "Repique rápido",
        "interval": "5m",
        "strategy": "rsi_bounce",
        "params": {"htf_ema": 1152},
        "risk": FAST_RISK,
        "description": (
            "Compra repiques curtos do RSI em candles de 5 minutos, só a favor da tendência de fundo (cerca de 4 dias) "
            "e com o sentimento do mercado subindo. Alvo parcial em +1%, stop curto e trailing. Foi o perfil rápido que "
            "menos perdeu, com oscilação pequena."
        ),
        "stats": {
            "cases": 28, "period_days": 45, "median_return_pct": -2.6, "profitable_pct": 7, "avg_drawdown_pct": -3.8,
            "worst_return_pct": -8.3, "trades_per_period": 14, "avg_trade_minutes": 46, "win_rate_pct": 36,
            "buy_hold_median_pct": 14.2, "median_return_bnb_pct": -1.2,
        },
    },
    {
        "key": "rapido_ignicao_15m",
        "tier": "rapido",
        "name": "Ignição rápida",
        "interval": "15m",
        "strategy": "ignition",
        "params": {"htf_ema": 384},
        "risk": FAST_RISK,
        "description": (
            "Candle de ignição em 15 minutos, só a favor da tendência de fundo e com o sentimento subindo. Sem custos, "
            "teria lucrado na maioria dos casos; com as taxas reais, perde, porque opera muito (cerca de 45 vezes em 4 meses)."
        ),
        "stats": {
            "cases": 28, "period_days": 120, "median_return_pct": -8.4, "profitable_pct": 4, "avg_drawdown_pct": -13.6,
            "worst_return_pct": -24.3, "trades_per_period": 45, "avg_trade_minutes": 96, "win_rate_pct": 36,
            "buy_hold_median_pct": 0.2, "median_return_bnb_pct": -4.4,
        },
    },
    {
        "key": "medio_ignicao_1h",
        "tier": "medio",
        "name": "Ignição 1h",
        "interval": "1h",
        "strategy": "ignition",
        "params": {},
        "risk": RISING_SLOW_RISK,
        "description": (
            "Candle de ignição em candles de 1 hora, comprando só com o sentimento do mercado subindo na semana. "
            "O filtro triplicou o resultado nos testes e reduziu as quedas, de forma parecida nos dois grupos de pares."
        ),
        "stats": {
            "cases": 42, "period_days": 180, "median_return_pct": 8.3, "profitable_pct": 62, "avg_drawdown_pct": -15.9,
            "worst_return_pct": -19.6, "trades_per_period": 24, "avg_trade_minutes": 1038, "win_rate_pct": 35,
            "buy_hold_median_pct": 10.2,
        },
    },
    {
        "key": "medio_hilo_2h",
        "tier": "medio",
        "name": "HiLo 2h com trailing",
        "interval": "2h",
        "strategy": "hilo_rsi",
        "params": {},
        "risk": MEDIUM_RISK,
        "description": (
            "HiLo + RSI em candles de 2 horas, com stop de 2× ATR, trailing stop e sem comprar no medo extremo. "
            "Lucrou num período em que só segurar a moeda perdeu 15,7%: foca em proteger o capital."
        ),
        "stats": {
            "cases": 28, "period_days": 240, "median_return_pct": 4.3, "profitable_pct": 64, "avg_drawdown_pct": -17.8,
            "worst_return_pct": -26.5, "trades_per_period": 24, "avg_trade_minutes": 1242, "win_rate_pct": 38,
            "buy_hold_median_pct": -15.7,
        },
    },
    {
        "key": "lento_squeeze_4h",
        "tier": "lento",
        "name": "Squeeze 4h",
        "interval": "4h",
        "strategy": "squeeze",
        "params": {},
        "risk": SLOW_RISK,
        "recommended": True,
        "description": (
            "A melhor relação entre resultado e risco nos testes: lucro em 73% dos casos e a menor queda máxima "
            "entre as estratégias de tendência. Não compra com medo extremo no mercado. Recomendado para começar."
        ),
        "stats": {
            "cases": 41, "period_days": 365, "median_return_pct": 23.3, "profitable_pct": 73, "avg_drawdown_pct": -23.3,
            "worst_return_pct": -36.7, "trades_per_period": 17, "avg_trade_minutes": 4368, "win_rate_pct": 38,
            "buy_hold_median_pct": 12.5,
        },
    },
    {
        "key": "lento_confluencia_1d",
        "tier": "lento",
        "name": "Confluência diária",
        "interval": "1d",
        "strategy": "confluence",
        "params": {},
        "risk": SLOW_RISK,
        "description": (
            "Candles diários: poucas operações, que duram semanas. Teve a maior chance de lucro (77%), mas oscila "
            "mais no caminho e a amostra é pequena (13 casos)."
        ),
        "stats": {
            "cases": 13, "period_days": 540, "median_return_pct": 23.1, "profitable_pct": 77, "avg_drawdown_pct": -40.6,
            "worst_return_pct": -35.7, "trades_per_period": 8, "avg_trade_minutes": 33120, "win_rate_pct": 38,
            "buy_hold_median_pct": -9.2,
        },
    },
]  # fmt: skip

FAST_INTERVALS = {"1m", "3m", "5m", "15m"}


def tier_of(interval: str) -> str:
    if interval in FAST_INTERVALS:
        return "rapido"
    if interval in {"30m", "1h", "2h"}:
        return "medio"
    return "lento"


def profiles_payload() -> dict:
    tiers = []
    for tier in TIERS:
        items = []
        for p in PROFILES:
            if p["tier"] != tier["key"]:
                continue
            strategy = STRATEGIES[p["strategy"]]
            items.append(
                {
                    **p,
                    "recommended": bool(p.get("recommended")),
                    "strategy_name": strategy.name,
                    "params": strategy.resolve_params(p["params"]),
                    "risk": RiskConfig(**{**RiskConfig().model_dump(), **p["risk"]}).model_dump(),
                }
            )
        tiers.append({**tier, "profiles": items})
    return {"tiers": tiers}
