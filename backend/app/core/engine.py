"""Motor de execução dos bots.

Cada bot em execução tem uma thread (BotRunner) que, a cada
`engine_poll_seconds`:
  1. Confere stop, break-even, trailing e alvos com o preço atual;
  2. Quando um candle novo fecha, roda a estratégia e compra/vende.

Toda a lógica de negociação de um bot fica em `BotService`, também usada
pela API (ex.: encerrar posição manualmente).
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import indicators as ta
from app.core import newsguard
from app.core.exchange import PaperTrader, SymbolRules, interval_ms, now_ms
from app.core.markets import EXCHANGE, EXCHANGE_LABEL, get_market
from app.core.okx import OkxMarketData, OkxTrader
from app.core.risk import PositionState, RiskConfig, open_position, position_size_quote, update
from app.core.sentiment import live_check as sentiment_check
from app.core.strategies import REMOVED, get_strategy
from app.db import session_scope
from app.models import Bot, BotEvent, Credential, Order, Position, SystemState, utcnow
from app.security import decrypt

log = logging.getLogger("bot_trader.engine")

MAX_CONSECUTIVE_ERRORS = 8
EVENTS_KEPT_PER_BOT = 1500


def add_event(db: Session, bot_id: int, level: str, message: str, data: dict | None = None) -> None:
    db.add(BotEvent(bot_id=bot_id, level=level, message=message, data=data))


def okx_credential(db: Session, user_id: int) -> Credential | None:
    return db.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == EXCHANGE))


def okx_secrets(cred: Credential) -> dict:
    """Segredo, passphrase e região da OKX (guardados juntos e criptografados)."""
    data = json.loads(decrypt(cred.secret_enc or ""))
    return {"secret": data["secret"], "passphrase": data["passphrase"], "region": data.get("region", "global")}


def make_live_trader(db: Session, bot: Bot) -> OkxTrader:
    cred = okx_credential(db, bot.user_id)
    if cred is None or not cred.secret_enc:
        raise RuntimeError(f"Chaves da {EXCHANGE_LABEL} não configuradas.")
    s = okx_secrets(cred)
    return OkxTrader(decrypt(cred.key_enc), s["secret"], s["passphrase"], demo=cred.testnet, region=s["region"])


def market_params(db: Session, user_id: int, mode: str) -> tuple[bool, str]:
    """(conta de demonstração?, região da conta) para os dados de mercado de um bot."""
    cred = okx_credential(db, user_id)
    demo = bool(cred and cred.testnet) and mode == "live"
    region = "global"
    if cred is not None:
        try:
            region = okx_secrets(cred)["region"]
        except (ValueError, KeyError):
            region = "global"
    return demo, region


def bot_market(db: Session, bot: Bot) -> OkxMarketData:
    demo, region = market_params(db, bot.user_id, bot.mode)
    return get_market(demo, region)


def migrate_to_okx(db: Session) -> int:
    """A Binance foi removida do sistema (set/2026): os bots passam para a OKX.

    - bots simulados seguem normalmente, com os preços da OKX;
    - bots reais ligados são desligados, para o usuário conferir e religar na OKX;
    - posição real aberta na Binance deixa de ser acompanhada (o aviso manda vender lá);
    - as chaves da Binance guardadas são apagadas.
    Devolve quantos bots foram migrados.
    """
    from app.account import audit  # evita import circular

    moved = 0
    for bot in db.scalars(select(Bot).where(Bot.exchange != EXCHANGE)):
        moved += 1
        pos = db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open"))
        if bot.mode == "live" and pos is not None:
            pos.status, pos.exit_reason, pos.exit_time = "closed", "migrated", utcnow()
            pos.qty = 0.0
            add_event(db, bot.id, "warn",
                      f"A Binance foi removida do sistema. A posição real aberta na Binance ({_fmt(pos.initial_qty)} {bot.base_asset}) "
                      "não é mais acompanhada: se ainda tiver essas moedas lá, venda manualmente na Binance.")  # fmt: skip
        if bot.mode == "live" and bot.status == "running":
            bot.status = "stopped"
            bot.status_reason = "Migrado da Binance para a OKX: confira as chaves da OKX em Configurações e ligue de novo."
        bot.exchange = EXCHANGE
        bot.last_candle_time = None
        add_event(db, bot.id, "info", "Bot migrado para a OKX (a Binance foi removida do sistema). Preços e ordens agora vêm da OKX.")
    for cred in db.scalars(select(Credential).where(Credential.provider == "binance")):
        audit(db, cred.user_id, "binance_keys_removed", None, "Binance removida do sistema")
        db.delete(cred)
    return moved


def _fmt(v: float) -> str:
    """Número no formato brasileiro (84.018,01), sem zeros sobrando."""
    text = f"{v:,.8f}" if abs(v) < 1 else f"{v:,.4f}"
    text = text.rstrip("0").rstrip(".")
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _signed(v: float) -> str:
    """Valor com sinal e 2 casas no formato brasileiro (+1.234,56)."""
    text = f"{v:+,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


class BotService:
    """Operações de um bot dentro de uma sessão de banco."""

    def __init__(self, db: Session, bot: Bot, market: OkxMarketData, trader):
        self.db = db
        self.bot = bot
        self.market = market
        self.trader = trader
        self.risk = RiskConfig(**(bot.risk or {}))
        self._rules: SymbolRules | None = None

    # ------------------------------------------------------------ utilidades

    @property
    def rules(self) -> SymbolRules:
        if self._rules is None:
            self._rules = self.market.symbol_rules(self.bot.symbol)
        return self._rules

    def event(self, level: str, message: str, data: dict | None = None) -> None:
        add_event(self.db, self.bot.id, level, message, data)

    def open_position(self) -> Position | None:
        return self.db.scalar(
            select(Position).where(Position.bot_id == self.bot.id, Position.status == "open").order_by(Position.id.desc())
        )

    def available_quote(self) -> float:
        if self.bot.mode == "paper":
            return self.bot.paper_balance
        return self.trader.free(self.rules.quote)

    @staticmethod
    def to_state(pos: Position) -> PositionState:
        return PositionState(
            entry_price=pos.entry_price,
            qty=pos.qty,
            initial_qty=pos.initial_qty,
            highest=pos.highest_price,
            stop=pos.stop_price,
            stop_kind=pos.stop_kind,
            tp_index=pos.tp_index,
            atr=pos.atr_at_entry,
            trailing_active=pos.trailing_active,
        )

    @staticmethod
    def apply_state(pos: Position, st: PositionState) -> None:
        pos.highest_price = st.highest
        pos.stop_price = st.stop
        pos.stop_kind = st.stop_kind
        pos.tp_index = st.tp_index
        pos.trailing_active = st.trailing_active

    # ------------------------------------------------------------ ciclo

    def step(self) -> None:
        pos = self.open_position()
        if pos is not None:
            self.manage_risk(pos, self.market.price(self.bot.symbol))
            if pos.status == "open":
                self.check_news_exit(pos)

        step_ms = interval_ms(self.bot.interval)
        last_closed_open = (now_ms() // step_ms) * step_ms - step_ms
        if self.bot.last_candle_time is not None and self.bot.last_candle_time >= last_closed_open:
            return
        self.evaluate(last_closed_open)

    def evaluate(self, expected_candle: int | None = None) -> None:
        strategy = get_strategy(self.bot.strategy)
        params = strategy.resolve_params(self.bot.strategy_params)
        df = self.market.klines(self.bot.symbol, self.bot.interval, limit=strategy.warmup(params) + 10)
        if df.empty or (expected_candle is not None and int(df["time"].iloc[-1]) < expected_candle):
            return  # a OKX ainda não publicou o candle; tenta no próximo ciclo

        out = strategy.run(df, params)
        snap = out.snapshot(-1)
        candle_time = int(df["time"].iloc[-1])
        close = float(df["close"].iloc[-1])
        snap.update({"candle_time": candle_time, "close": close, "evaluated_at": utcnow().isoformat()})
        self.bot.last_signal = snap
        self.bot.last_candle_time = candle_time
        atr_series = ta.atr(df["high"], df["low"], df["close"], 14)
        atr_value = float(atr_series.iloc[-1]) if atr_series.notna().iloc[-1] else None

        pos = self.open_position()
        market_ok, market_reason, snap["market"] = self.market_filters()
        met = sum(c["ok"] for c in snap["entry_checks"])
        total = len(snap["entry_checks"])
        if pos is None and snap["entry"]:
            allowed, reason = self.can_enter()
            if allowed and not market_ok:
                allowed, reason = False, market_reason
            if allowed:
                self.buy(atr_value, "signal")
            else:
                self.event("warn", f"Sinal de compra ignorado: {reason}", snap)
        elif pos is not None and snap["exit"]:
            triggered = [c["label"] for c in snap["exit_checks"] if c["ok"]]
            self.event("signal", f"Sinal de venda: {', '.join(triggered)}", snap)
            self.sell(pos, 1.0, "signal")
        else:
            state = "posicionado" if pos else f"entrada {met}/{total} condições"
            self.event("signal", f"Candle fechado em {_fmt(close)}: sem ação ({state})", snap)

    def market_filters(self) -> tuple[bool, str, dict]:
        """Sentimento do mercado e notícias: (pode comprar?, motivo do bloqueio, leitura para a tela)."""
        info: dict = {"sentiment_filter": self.risk.sentiment_filter, "news_guard": self.risk.news_guard}
        ok, reason = True, ""
        try:
            allowed, why, fng = sentiment_check(self.risk.sentiment_filter, self.risk.fear_threshold)
            info["sentiment"] = fng
            if not allowed:
                ok, reason = False, why
        except Exception as exc:  # sem o índice, o filtro não bloqueia
            log.warning("Índice de medo e ganância indisponível: %s", exc)
        item = newsguard.entry_block(self.db, self.bot.base_asset, self.risk.news_guard, self.risk.news_window_hours)
        if item is not None:
            info["news_block"] = {"title": item.title, "source": item.source, "url": item.url, "published_at": item.published_at.isoformat(), "sentiment": item.sentiment}
            if ok:
                ok, reason = False, f"notícia negativa de alto impacto: {newsguard.describe(item)}"
        info["blocks_entry"] = not ok
        info["reason"] = reason
        return ok, reason, info

    def check_news_exit(self, pos: Position) -> None:
        if self.risk.news_guard != "block_and_exit" or pos.entry_time is None:
            return
        item = newsguard.exit_trigger(self.db, self.bot.base_asset, self.risk.news_guard, self.risk.news_window_hours, pos.entry_time)
        if item is None:
            return
        self.event("warn", f"Notícia muito negativa confirmada pela IA: {newsguard.describe(item)}. Vendendo a posição.", {"url": item.url})
        self.sell(pos, 1.0, "news")

    def can_enter(self) -> tuple[bool, str]:
        last = self.db.scalar(
            select(Position)
            .where(Position.bot_id == self.bot.id, Position.status == "closed")
            .order_by(Position.exit_time.desc())
        )
        if last is not None and last.exit_time is not None and self.risk.cooldown_bars > 0:
            wait = timedelta(milliseconds=interval_ms(self.bot.interval) * self.risk.cooldown_bars)
            if utcnow() - last.exit_time < wait:
                n = self.risk.cooldown_bars
                return False, f"pausa de {n} candle{'s' if n > 1 else ''} após a última saída"
        if self.risk.max_daily_loss_quote > 0:
            start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today = self.db.scalar(
                select(func.coalesce(func.sum(Position.pnl_quote), 0.0)).where(
                    Position.bot_id == self.bot.id, Position.status == "closed", Position.exit_time >= start
                )
            )
            if today <= -self.risk.max_daily_loss_quote:
                return False, f"limite de perda diária atingido ({_fmt(today)} {self.bot.quote_asset})"
        return True, ""

    # ------------------------------------------------------------ execução

    def buy(self, atr_value: float | None, reason: str) -> Position | None:
        rules = self.rules
        price = self.market.price(self.bot.symbol)
        available = self.available_quote()
        size = position_size_quote(self.risk, available, available, price, atr_value)
        if size < rules.min_notional * 1.02:
            self.event(
                "warn",
                f"Compra não enviada: tamanho {_fmt(size)} {rules.quote} abaixo do mínimo da OKX "
                f"({_fmt(rules.min_notional)}) ou saldo insuficiente ({_fmt(available)}).",
            )
            return None

        fill = self.trader.market_buy_quote(self.bot.symbol, size, rules)
        if fill.qty <= 0:
            self.event("error", "Ordem de compra sem execução.", {"raw": fill.raw})
            return None

        state = open_position(fill.avg_price, fill.net_qty, atr_value, self.risk)
        pos = Position(
            bot_id=self.bot.id,
            symbol=self.bot.symbol,
            mode=self.bot.mode,
            strategy=self.bot.strategy,
            status="open",
            entry_price=fill.avg_price,
            entry_time=utcnow(),
            initial_qty=fill.net_qty,
            qty=fill.net_qty,
            cost_quote=fill.net_quote,
            fees_quote=fill.fee_quote,
            highest_price=fill.avg_price,
            stop_price=state.stop,
            stop_kind=state.stop_kind,
            atr_at_entry=atr_value,
        )
        self.db.add(pos)
        self.db.flush()
        if self.bot.mode == "paper":
            self.bot.paper_balance -= fill.net_quote
        self._record_order(pos, fill, reason)
        stop_txt = f", stop {_fmt(state.stop)}" if state.stop else ""
        self.event(
            "trade",
            f"COMPRA {_fmt(fill.net_qty)} {rules.base} a {_fmt(fill.avg_price)} ({_fmt(fill.net_quote)} {rules.quote}){stop_txt}",
            {"position_id": pos.id, "reason": reason},
        )
        return pos

    def sell(self, pos: Position, fraction: float, reason: str) -> bool:
        rules = self.rules
        price = self.market.price(self.bot.symbol)
        qty = pos.qty * min(max(fraction, 0.0), 1.0)
        # não deixa sobrar "poeira" impossível de vender
        if fraction < 1.0 and not rules.is_tradeable(pos.qty - qty, price):
            qty, fraction = pos.qty, 1.0
        if self.bot.mode == "live":
            qty = min(qty, self.trader.free(rules.base))

        if not rules.is_tradeable(qty, price):
            if fraction >= 1.0:
                # resto pequeno demais para a OKX vender: encerra o registro
                self._write_off(pos, price)
                self._close(pos, reason)
                self.event("warn", f"Posição encerrada com resto abaixo do mínimo negociável ({_fmt(qty)} {rules.base}).")
                return True
            self.event("warn", f"Venda parcial ({reason}) abaixo do mínimo negociável; ignorada.")
            return False

        fill = self.trader.market_sell_qty(self.bot.symbol, qty, rules)
        if fill.qty <= 0:
            self.event("error", "Ordem de venda sem execução.", {"raw": fill.raw})
            return False

        pos.qty = max(pos.qty - fill.qty, 0.0)
        pos.sold_qty += fill.qty
        pos.proceeds_quote += fill.net_quote
        pos.gross_sold_quote += fill.quote
        pos.fees_quote += fill.fee_quote
        if self.bot.mode == "paper":
            self.bot.paper_balance += fill.net_quote
        self._record_order(pos, fill, reason)

        closed = fraction >= 1.0 or pos.qty < rules.step_size or not rules.is_tradeable(pos.qty, price)
        label = REASON_LABELS.get(reason, reason)
        if closed:
            self._write_off(pos, price)  # resto de arredondamento
            self._close(pos, reason)
            self.event(
                "trade",
                f"VENDA ({label}) {_fmt(fill.qty)} {rules.base} a {_fmt(fill.avg_price)}. "
                f"Resultado: {_signed(pos.pnl_quote)} {rules.quote} ({_signed(pos.pnl_pct)}%)",
                {"position_id": pos.id, "reason": reason},
            )
        else:
            self.event(
                "trade",
                f"VENDA PARCIAL ({label}) {_fmt(fill.qty)} {rules.base} a {_fmt(fill.avg_price)} "
                f"({_fmt(fill.net_quote)} {rules.quote})",
                {"position_id": pos.id, "reason": reason},
            )
        return True

    def manage_risk(self, pos: Position, price: float) -> None:
        state = self.to_state(pos)
        actions = update(state, self.risk, price, price)
        self.apply_state(pos, state)
        for action in actions:
            if not self.sell(pos, action.fraction, action.reason) or pos.status == "closed":
                break

    def _write_off(self, pos: Position, price: float) -> None:
        """Zera o resto que não dá para vender. No simulado ele é creditado ao preço atual;
        no real ele continua na carteira e não entra no resultado (não foi vendido)."""
        leftover = pos.qty
        if leftover <= 0:
            return
        if self.bot.mode == "paper":
            value = leftover * price * (1 - self.risk.fee_pct / 100)
            pos.proceeds_quote += value
            pos.gross_sold_quote += leftover * price
            pos.sold_qty += leftover
            self.bot.paper_balance += value
        pos.qty = 0.0

    def _close(self, pos: Position, reason: str) -> None:
        pos.status = "closed"
        pos.exit_time = utcnow()
        pos.exit_reason = reason
        pos.exit_price = pos.gross_sold_quote / pos.sold_qty if pos.sold_qty else None
        pos.pnl_quote = pos.proceeds_quote - pos.cost_quote
        pos.pnl_pct = pos.pnl_quote / pos.cost_quote * 100 if pos.cost_quote else 0.0

    def _record_order(self, pos: Position, fill, reason: str) -> None:
        self.db.add(
            Order(
                bot_id=self.bot.id,
                position_id=pos.id,
                mode=self.bot.mode,
                symbol=self.bot.symbol,
                side=fill.side,
                exchange_order_id=fill.order_id,
                status=fill.status,
                price=fill.avg_price,
                qty=fill.qty,
                quote_qty=fill.quote,
                fee_quote=fill.fee_quote,
                reason=reason,
                raw=fill.raw or None,
            )
        )


REASON_LABELS = {
    "signal": "sinal da estratégia",
    "stop_loss": "stop loss",
    "breakeven": "break-even",
    "trailing_stop": "trailing stop",
    "take_profit": "alvo parcial",
    "manual": "manual",
    "news": "notícia negativa",
    "migrated": "migrada da Binance",
}


# ---------------------------------------------------------------------------


class BotRunner(threading.Thread):
    def __init__(self, bot_id: int, manager: "BotManager"):
        super().__init__(daemon=True, name=f"bot-{bot_id}")
        self.bot_id = bot_id
        self.manager = manager
        self.stop_event = threading.Event()
        self.errors = 0
        self._trader = None
        self._trader_key = None

    def stop(self) -> None:
        self.stop_event.set()

    def _trader_for(self, db: Session, bot: Bot, market: OkxMarketData):
        if bot.mode == "paper":
            return self.manager.paper_trader_factory(market, RiskConfig(**(bot.risk or {})).fee_pct)
        cred = okx_credential(db, bot.user_id)
        key = (cred.id, cred.updated_at) if cred else None
        if self._trader is None or self._trader_key != key:
            self._trader = self.manager.live_trader_factory(db, bot)
            self._trader_key = key
        return self._trader

    def tick(self) -> bool:
        with self.manager.bot_lock(self.bot_id), session_scope() as db:
            bot = db.get(Bot, self.bot_id)
            if bot is None or bot.status != "running":
                return False
            market = self.manager.market_for(db, bot)
            service = BotService(db, bot, market, self._trader_for(db, bot, market))
            service.step()
            bot.last_tick_at = utcnow()
            bot.last_error = ""
        return True

    def run(self) -> None:
        self.manager._runner_started(self.bot_id)
        try:
            while not self.stop_event.is_set():
                try:
                    if not self.tick():
                        break
                    self.errors = 0
                    self.manager._maybe_prune()
                except Exception as exc:  # erros de rede/API não derrubam o bot de primeira
                    self.errors += 1
                    log.exception("Erro no bot %s", self.bot_id)
                    self._record_error(exc)
                    if self.errors >= MAX_CONSECUTIVE_ERRORS:
                        self._fail(exc)
                        break
                backoff = min(2 ** max(self.errors - 1, 0), 16) if self.errors else 1
                self.stop_event.wait(get_settings().engine_poll_seconds * backoff)
        finally:
            self.manager._runner_finished(self.bot_id, self)

    def _record_error(self, exc: Exception) -> None:
        try:
            with session_scope() as db:
                bot = db.get(Bot, self.bot_id)
                if bot:
                    bot.last_error = str(exc)[:500]
                add_event(db, self.bot_id, "error", f"Erro ({self.errors}/{MAX_CONSECUTIVE_ERRORS}): {exc}")
        except Exception:
            log.exception("Falha ao registrar erro do bot %s", self.bot_id)

    def _fail(self, exc: Exception) -> None:
        with session_scope() as db:
            bot = db.get(Bot, self.bot_id)
            if bot:
                bot.status = "error"
                bot.status_reason = f"Parado após {MAX_CONSECUTIVE_ERRORS} erros seguidos: {exc}"[:255]
            add_event(db, self.bot_id, "error", "Bot parado por erros consecutivos. Verifique e reinicie.")


class BotManager:
    def __init__(self):
        self.runners: dict[int, BotRunner] = {}
        self._lock = threading.RLock()
        self._bot_locks: dict[int, threading.Lock] = {}
        self.started_at: datetime | None = None
        self._last_prune = 0.0
        # pontos de injeção (usados nos testes)
        self.market_factory = bot_market
        self.live_trader_factory = make_live_trader
        self.paper_trader_factory = lambda market, fee_pct: PaperTrader(market, fee_pct)

    def market_for(self, db: Session, bot: Bot) -> OkxMarketData:
        return self.market_factory(db, bot)

    def bot_lock(self, bot_id: int) -> threading.Lock:
        with self._lock:
            return self._bot_locks.setdefault(bot_id, threading.Lock())

    # ------------------------------------------------------------ estado global

    @staticmethod
    def _system(db: Session) -> SystemState:
        state = db.get(SystemState, 1)
        if state is None:
            state = SystemState(id=1, engine_enabled=True)
            db.add(state)
            db.flush()
        return state

    def engine_enabled(self) -> bool:
        with session_scope() as db:
            return self._system(db).engine_enabled

    def start(self) -> None:
        self.started_at = utcnow()
        with session_scope() as db:
            enabled = self._system(db).engine_enabled
            # bots com estratégias removidas passam para a substituta, com parâmetros padrão
            for bot in db.scalars(select(Bot).where(Bot.strategy.in_(list(REMOVED)))):
                old, new = bot.strategy, get_strategy(bot.strategy)
                bot.strategy, bot.strategy_params = new.key, new.resolve_params(None)
                bot.last_candle_time = None
                add_event(db, bot.id, "warn", f"A estratégia '{old}' foi removida por desempenho fraco nos testes. Bot migrado para '{new.name}' com parâmetros padrão.")
            # recupera o tempo de execução de bots interrompidos por queda do servidor
            for bot in db.scalars(select(Bot).where(Bot.started_at.is_not(None))):
                if bot.last_tick_at and bot.last_tick_at > bot.started_at:
                    bot.total_runtime_seconds += (bot.last_tick_at - bot.started_at).total_seconds()
                bot.started_at = None
            ids = list(db.scalars(select(Bot.id).where(Bot.status == "running")))
        if enabled:
            for bot_id in ids:
                self.spawn(bot_id)

    def set_engine(self, enabled: bool) -> None:
        with session_scope() as db:
            self._system(db).engine_enabled = enabled
            ids = list(db.scalars(select(Bot.id).where(Bot.status == "running")))
        if enabled:
            for bot_id in ids:
                self.spawn(bot_id)
        else:
            self.stop_all()

    # ------------------------------------------------------------ bots

    def spawn(self, bot_id: int) -> None:
        with self._lock:
            runner = self.runners.get(bot_id)
            if runner is not None and runner.is_alive() and not runner.stop_event.is_set():
                return
            runner = BotRunner(bot_id, self)
            self.runners[bot_id] = runner
            runner.start()

    def start_bot(self, bot_id: int) -> None:
        if self.engine_enabled():
            self.spawn(bot_id)

    def stop_bot(self, bot_id: int) -> None:
        with self._lock:
            runner = self.runners.get(bot_id)
        if runner is not None:
            runner.stop()

    def is_running(self, bot_id: int) -> bool:
        runner = self.runners.get(bot_id)
        return runner is not None and runner.is_alive() and not runner.stop_event.is_set()

    def running_count(self) -> int:
        return sum(1 for bot_id in list(self.runners) if self.is_running(bot_id))

    def stop_all(self, join: bool = False) -> None:
        with self._lock:
            runners = list(self.runners.values())
        for runner in runners:
            runner.stop()
        if join:
            for runner in runners:
                runner.join(timeout=10)

    def shutdown(self) -> None:
        self.stop_all(join=True)

    # ------------------------------------------------------------ callbacks das threads

    def _runner_started(self, bot_id: int) -> None:
        with session_scope() as db:
            bot = db.get(Bot, bot_id)
            if bot:
                bot.started_at = utcnow()
                add_event(db, bot_id, "info", f"Bot iniciado ({'SIMULADO' if bot.mode == 'paper' else 'REAL'}).")

    def _runner_finished(self, bot_id: int, runner: BotRunner) -> None:
        try:
            with session_scope() as db:
                bot = db.get(Bot, bot_id)
                if bot and bot.started_at:
                    bot.total_runtime_seconds += (utcnow() - bot.started_at).total_seconds()
                    bot.started_at = None
                    add_event(db, bot_id, "info", "Bot parado.")
            self._maybe_prune()
        finally:
            with self._lock:
                if self.runners.get(bot_id) is runner:
                    del self.runners[bot_id]

    def _maybe_prune(self) -> None:
        if time.time() - self._last_prune < 3600:
            return
        self._last_prune = time.time()
        with session_scope() as db:
            for bot_id in db.scalars(select(Bot.id)):
                cutoff = db.scalar(
                    select(BotEvent.id)
                    .where(BotEvent.bot_id == bot_id)
                    .order_by(BotEvent.id.desc())
                    .offset(EVENTS_KEPT_PER_BOT)
                    .limit(1)
                )
                if cutoff:
                    db.execute(delete(BotEvent).where(BotEvent.bot_id == bot_id, BotEvent.id <= cutoff))


manager = BotManager()
