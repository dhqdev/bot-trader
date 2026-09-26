"""Contrato comum de todas as estratégias.

Uma estratégia recebe um DataFrame OHLCV **só com candles fechados**
(colunas: time, open, high, low, close, volume) e devolve séries booleanas
de entrada e saída para todas as barras. O motor (ao vivo ou backtest)
decide o que fazer com elas; stop, alvo e trailing ficam no gerenciador
de risco, separado da estratégia.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

ParamType = Literal["int", "float", "bool", "select"]


@dataclass
class Param:
    name: str
    label: str
    type: ParamType
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    help: str = ""
    labels: list[str] | None = None  # rótulos legíveis das opções (mesma ordem de options)


@dataclass
class Check:
    label: str
    ok: bool


@dataclass
class StrategyOutput:
    entry: pd.Series
    exit: pd.Series
    entry_conditions: dict[str, pd.Series] = field(default_factory=dict)
    exit_conditions: dict[str, pd.Series] = field(default_factory=dict)
    overlays: dict[str, pd.Series] = field(default_factory=dict)  # linhas no gráfico de preço
    values: dict[str, pd.Series] = field(default_factory=dict)  # leituras exibidas (RSI, ADX...)

    def snapshot(self, idx: int = -1) -> dict:
        """Resumo legível da barra `idx` para a interface e para a IA."""

        def _val(s: pd.Series) -> float | None:
            v = s.iloc[idx]
            return None if pd.isna(v) else round(float(v), 6)

        return {
            "entry": bool(self.entry.iloc[idx]),
            "exit": bool(self.exit.iloc[idx]),
            "entry_checks": [asdict(Check(k, bool(v.iloc[idx]))) for k, v in self.entry_conditions.items()],
            "exit_checks": [asdict(Check(k, bool(v.iloc[idx]))) for k, v in self.exit_conditions.items()],
            "values": {k: _val(v) for k, v in self.values.items()},
        }


def all_of(conds: dict[str, pd.Series]) -> pd.Series:
    out = None
    for s in conds.values():
        s = s.fillna(False).astype(bool)
        out = s if out is None else (out & s)
    return out


def any_of(conds: dict[str, pd.Series]) -> pd.Series:
    out = None
    for s in conds.values():
        s = s.fillna(False).astype(bool)
        out = s if out is None else (out | s)
    return out


def always(index: pd.Index, value: bool = True) -> pd.Series:
    return pd.Series(np.full(len(index), value), index=index)


class Strategy(ABC):
    key: str
    name: str
    style: str  # tendência, reversão, rompimento, momentum, confluência
    description: str
    params: list[Param]
    ordered: tuple[tuple[str, str], ...] = ()  # pares (rápido, lento) que precisam de rápido < lento

    def resolve_params(self, raw: dict | None) -> dict:
        """Aplica os padrões, converte os tipos e limita aos intervalos permitidos."""
        raw = raw or {}
        out = {}
        for p in self.params:
            value = raw.get(p.name, p.default)
            try:
                if p.type == "int":
                    value = int(round(float(value)))
                elif p.type == "float":
                    value = float(value)
                elif p.type == "bool":
                    value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
                elif p.type == "select":
                    value = str(value) if str(value) in (p.options or []) else p.default
            except (TypeError, ValueError):
                value = p.default
            if p.type in ("int", "float"):
                if p.min is not None:
                    value = max(value, p.min if p.type == "float" else int(p.min))
                if p.max is not None:
                    value = min(value, p.max if p.type == "float" else int(p.max))
            out[p.name] = value
        for fast, slow in self.ordered:
            if out[fast] >= out[slow]:
                out[fast], out[slow] = min(out[fast], out[slow]), max(out[fast], out[slow])
                if out[fast] == out[slow]:
                    out[slow] = out[fast] + 1
        return out

    def warmup(self, p: dict) -> int:
        """Quantidade mínima de candles para os indicadores estabilizarem."""
        longest = max([int(v) for k, v in p.items() if isinstance(v, int) and not isinstance(v, bool)] + [50])
        return longest * 3

    @abstractmethod
    def compute(self, df: pd.DataFrame, p: dict) -> StrategyOutput: ...

    def run(self, df: pd.DataFrame, raw_params: dict | None = None) -> StrategyOutput:
        p = self.resolve_params(raw_params)
        out = self.compute(df, p)
        out.entry = out.entry.fillna(False).astype(bool)
        out.exit = out.exit.fillna(False).astype(bool)
        return out

    def describe(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "style": self.style,
            "description": self.description,
            "params": [asdict(p) for p in self.params],
        }
