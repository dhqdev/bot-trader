from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.exchange import INTERVAL_MINUTES
from app.core.risk import RiskConfig
from app.core.strategies import DEFAULT_INTERVAL, DEFAULT_STRATEGY, STRATEGIES


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field("", max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("E-mail inválido")
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class TwoFactorLoginIn(BaseModel):
    ticket: str = Field(max_length=2000)
    code: str = Field(min_length=6, max_length=32)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class StepUpIn(BaseModel):
    """Confirmação para ações sensíveis: senha e, se ativado, o código de 2 etapas."""

    password: str = Field("", max_length=128)
    code: str | None = Field(None, max_length=32)


class TwoFactorCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class OkxKeysIn(StepUpIn):
    api_key: str = Field(min_length=10, max_length=256)
    api_secret: str = Field(min_length=10, max_length=256)
    passphrase: str = Field(min_length=1, max_length=128)
    demo: bool = False  # chaves criadas no "Demo Trading" da OKX
    region: Literal["global", "eea", "us"] = "global"


class AnthropicKeyIn(StepUpIn):
    api_key: str = Field(min_length=10, max_length=512)


class OpenAIKeyIn(StepUpIn):
    api_key: str = Field(min_length=10, max_length=512)
    model: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9._:-]*$")


class OpenAIModelIn(BaseModel):
    model: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class AIProviderIn(BaseModel):
    provider: Literal["anthropic", "openai"]


class EngineIn(BaseModel):
    enabled: bool


def _check_interval(v: str) -> str:
    if v not in INTERVAL_MINUTES:
        raise ValueError(f"Intervalo inválido. Use um de: {', '.join(INTERVAL_MINUTES)}")
    return v


def _check_strategy(v: str) -> str:
    if v not in STRATEGIES:
        raise ValueError(f"Estratégia inválida. Use uma de: {', '.join(STRATEGIES)}")
    return v


class BotIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=4, max_length=32)
    interval: str = DEFAULT_INTERVAL
    strategy: str = DEFAULT_STRATEGY
    strategy_params: dict = Field(default_factory=dict)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    mode: Literal["paper", "live"] = "paper"
    paper_initial_balance: float = Field(1000.0, gt=0, le=10_000_000)

    @field_validator("interval")
    @classmethod
    def _interval(cls, v: str) -> str:
        return _check_interval(v)

    @field_validator("strategy")
    @classmethod
    def _strategy(cls, v: str) -> str:
        return _check_strategy(v)

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        return v.strip().upper().replace("/", "").replace("-", "")


class BotUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    interval: str | None = None
    strategy: str | None = None
    strategy_params: dict | None = None
    risk: RiskConfig | None = None
    mode: Literal["paper", "live"] | None = None

    @field_validator("interval")
    @classmethod
    def _interval(cls, v):
        return None if v is None else _check_interval(v)

    @field_validator("strategy")
    @classmethod
    def _strategy(cls, v):
        return None if v is None else _check_strategy(v)


class BacktestIn(BaseModel):
    symbol: str = Field(min_length=4, max_length=32)
    interval: str = DEFAULT_INTERVAL
    strategy: str = DEFAULT_STRATEGY
    params: dict = Field(default_factory=dict)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    days: int = Field(365, ge=3, le=730)
    initial_capital: float = Field(1000.0, gt=0, le=10_000_000)

    @field_validator("interval")
    @classmethod
    def _interval(cls, v: str) -> str:
        return _check_interval(v)

    @field_validator("strategy")
    @classmethod
    def _strategy(cls, v: str) -> str:
        return _check_strategy(v)

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        return v.strip().upper().replace("/", "")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=40_000)


class ChatContext(BaseModel):
    bot_id: int | None = None
    backtest: dict | None = None  # resumo de um backtest exibido na tela


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)
    context: ChatContext = Field(default_factory=ChatContext)
    save_report: bool = False
    title: str = Field("", max_length=200)
