from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """SQLite não guarda fuso; gravamos e lemos tudo como UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Credential(Base):
    """Chaves de API criptografadas (OKX, Anthropic, OpenAI)."""

    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))  # okx | anthropic | openai
    key_enc: Mapped[str] = mapped_column(Text)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    testnet: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class SystemState(Base):
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    engine_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    symbol: Mapped[str] = mapped_column(String(32))
    base_asset: Mapped[str] = mapped_column(String(16))
    quote_asset: Mapped[str] = mapped_column(String(16))
    interval: Mapped[str] = mapped_column(String(8))
    # corretora do bot. Hoje sempre "okx"; bots antigos da Binance são migrados na inicialização
    exchange: Mapped[str] = mapped_column(String(16), default="okx", server_default="okx")
    strategy: Mapped[str] = mapped_column(String(64))
    strategy_params: Mapped[dict] = mapped_column(JSON, default=dict)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(8), default="paper")  # paper | live

    # desired state: stopped | running | paused | error
    status: Mapped[str] = mapped_column(String(16), default="stopped")
    status_reason: Mapped[str] = mapped_column(String(255), default="")

    paper_initial_balance: Mapped[float] = mapped_column(Float, default=1000.0)
    paper_balance: Mapped[float] = mapped_column(Float, default=1000.0)

    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    total_runtime_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    last_tick_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_candle_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # ms (open time)
    last_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(8))
    strategy: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(8), default="open", index=True)  # open | closed

    entry_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    initial_qty: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)  # quantidade restante
    cost_quote: Mapped[float] = mapped_column(Float)  # quanto foi gasto na compra (com taxa)
    proceeds_quote: Mapped[float] = mapped_column(Float, default=0.0)  # recebido nas vendas (líquido)
    sold_qty: Mapped[float] = mapped_column(Float, default=0.0)
    gross_sold_quote: Mapped[float] = mapped_column(Float, default=0.0)
    fees_quote: Mapped[float] = mapped_column(Float, default=0.0)

    # estado do gerenciamento de risco
    highest_price: Mapped[float] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_kind: Mapped[str] = mapped_column(String(16), default="stop_loss")
    trailing_active: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_index: Mapped[int] = mapped_column(Integer, default=0)
    atr_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)

    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    exit_reason: Mapped[str] = mapped_column(String(32), default="")
    pnl_quote: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    exchange_order_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="FILLED")
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    quote_qty: Mapped[float] = mapped_column(Float)
    fee_quote: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(32), default="signal")
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)


class BotEvent(Base):
    __tablename__ = "bot_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info | signal | trade | warn | error
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


# ---------------------------------------------------------------------------
# Tabelas da v2.2. São todas novas (create_all cria sozinho), para não precisar
# alterar colunas de tabelas que já existem nos bancos em produção.


class UserSecurity(Base):
    """Segurança da conta: verificação em duas etapas (2FA) e versão das sessões."""

    __tablename__ = "user_security"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int] = mapped_column(BigInteger, default=0)  # impede reusar o mesmo código
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)  # só os hashes
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # +1 derruba todas as sessões
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class SecurityEvent(Base):
    """Registro de atividade da conta (login, troca de senha, chaves, 2FA...)."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    source: Mapped[str] = mapped_column(String(64))
    lang: Mapped[str] = mapped_column(String(8), default="en")
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(TZDateTime(), index=True)
    fetched_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    assets: Mapped[list] = mapped_column(JSON, default=list)  # ex.: ["BTC", "ETH"] ou ["MARKET"]
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1 (muito negativa) a +1
    impact: Mapped[str] = mapped_column(String(8), default="low")  # low | medium | high
    category: Mapped[str] = mapped_column(String(24), default="other")
    classified_by: Mapped[str] = mapped_column(String(12), default="keywords")  # keywords | ai
    ai_summary: Mapped[str] = mapped_column(Text, default="")


class FearGreed(Base):
    """Índice de Medo e Ganância do mercado cripto (alternative.me), um valor por dia."""

    __tablename__ = "fear_greed"

    day: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # ms, 00:00 UTC
    value: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(32), default="")


class AutopilotConfig(Base):
    """Piloto automático de um bot: analisa, testa e (se autorizado) aplica melhorias."""

    __tablename__ = "autopilot"

    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), default="off")  # off | suggest | auto_paper | auto_all
    interval_hours: Mapped[int] = mapped_column(Integer, default=168)
    allow_strategy_change: Mapped[bool] = mapped_column(Boolean, default=True)
    live_authorized_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class OptimizationRun(Base):
    """Um ciclo do piloto automático: diagnóstico, candidatas testadas e decisão."""

    __tablename__ = "optimization_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | schedule
    # running | suggested | applied | rejected | reverted | no_change | failed | superseded
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tested: Mapped[list | None] = mapped_column(JSON, nullable=True)
    previous_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_notes: Mapped[str] = mapped_column(Text, default="")
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AIInsight(Base):
    """Base de conhecimento que a IA acumula e reutiliza nos próximos ciclos."""

    __tablename__ = "ai_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), default="")
    interval: Mapped[str] = mapped_column(String(8), default="")
    kind: Mapped[str] = mapped_column(String(16), default="lesson")  # lesson | warning | observation
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | optimizer
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class CandleCache(Base):
    """Candles fechados já baixados da OKX (não mudam): backtests e o piloto só buscam o que falta."""

    __tablename__ = "candle_cache"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    interval: Mapped[str] = mapped_column(String(8), primary_key=True)
    time: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # ms, abertura do candle
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class KVSetting(Base):
    """Estado global pequeno (ex.: última coleta de notícias)."""

    __tablename__ = "kv_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Modo automático (v2.6). Também são tabelas novas.


class AutoTrader(Base):
    """Modo automático de um usuário: a IA escolhe moedas e robôs, divide o valor e troca quem vai mal."""

    __tablename__ = "auto_trader"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(8), default="paper")  # paper | live
    budget: Mapped[float] = mapped_column(Float, default=1000.0)  # USDT que a IA pode usar no total
    max_robots: Mapped[int] = mapped_column(Integer, default=3)
    live_authorized_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    paused_reason: Mapped[str] = mapped_column(String(300), default="")  # proteção contra perdas
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)  # a proteção conta daqui
    last_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class AutoRobot(Base):
    """Robô criado pelo modo automático e o que a IA esperava dele."""

    __tablename__ = "auto_robots"

    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # active | retiring (não compra mais; para ao vender a posição) | retired
    state: Mapped[str] = mapped_column(String(12), default="active", index=True)
    allocation: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(8), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # resultado no teste quando foi escolhido
    retire_reason: Mapped[str] = mapped_column(String(300), default="")
    # encerrado por ir mal: a mesma moeda + estratégia não volta antes disso
    cooldown_until: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    retired_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AutoCycle(Base):
    """Um ciclo do modo automático: o que foi testado, o que a IA decidiu e o que mudou."""

    __tablename__ = "auto_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")  # start | manual | schedule
    status: Mapped[str] = mapped_column(String(12), default="running", index=True)  # running | done | failed
    summary: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSON, default=list)
    pool: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
