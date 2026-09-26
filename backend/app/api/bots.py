from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.engine import BotService, add_event, binance_credential, make_live_trader, manager
from app.core.exchange import PaperTrader, get_market, interval_ms, now_ms
from app.core.risk import RiskConfig
from app.core.strategies import get_strategy
from app.db import get_db
from app.deps import get_current_user, get_user_bot
from app.models import Bot, BotEvent, Order, Position, User
from app.schemas import BotIn, BotUpdate
from app.services.stats import bot_summary, position_view, price_for

router = APIRouter(prefix="/bots", tags=["bots"])


def _require_live_ready(db: Session, bot: Bot) -> None:
    if bot.mode == "live" and binance_credential(db, bot.user_id) is None:
        raise HTTPException(400, "Cadastre as chaves da Binance em Configurações antes de operar em modo real.")


@router.get("")
def list_bots(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bots = db.scalars(select(Bot).where(Bot.user_id == user.id).order_by(Bot.id))
    return [bot_summary(db, b) for b in bots]


@router.post("")
def create_bot(body: BotIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        rules = get_market().symbol_rules(body.symbol)
    except Exception as exc:
        raise HTTPException(400, f"Par inválido ou Binance indisponível: {exc}") from exc
    strategy = get_strategy(body.strategy)
    bot = Bot(
        user_id=user.id,
        name=body.name.strip(),
        symbol=body.symbol,
        base_asset=rules.base,
        quote_asset=rules.quote,
        interval=body.interval,
        strategy=body.strategy,
        strategy_params=strategy.resolve_params(body.strategy_params),
        risk=body.risk.model_dump(),
        mode=body.mode,
        paper_initial_balance=body.paper_initial_balance,
        paper_balance=body.paper_initial_balance,
        status="stopped",
    )
    _require_live_ready(db, bot)
    db.add(bot)
    db.flush()
    add_event(db, bot.id, "info", f"Bot criado ({strategy.name}, {bot.symbol} {bot.interval}).")
    db.commit()
    return bot_summary(db, bot)


@router.get("/{bot_id}")
def get_bot(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    return bot_summary(db, bot)


@router.put("/{bot_id}")
def update_bot(body: BotUpdate, bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    open_pos = db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open"))
    changes = body.model_dump(exclude_unset=True)
    if "mode" in changes and changes["mode"] != bot.mode:
        if open_pos:
            raise HTTPException(400, "Encerre a posição aberta antes de trocar entre simulado e real.")
        if bot.status == "running":
            raise HTTPException(400, "Pare o bot antes de trocar o modo.")
        bot.mode = changes["mode"]
        _require_live_ready(db, bot)
    if body.name is not None:
        bot.name = body.name.strip()
    if body.strategy is not None and body.strategy != bot.strategy:
        bot.strategy = body.strategy
        bot.last_candle_time = None
    if body.strategy_params is not None or body.strategy is not None:
        params = body.strategy_params if body.strategy_params is not None else bot.strategy_params
        bot.strategy_params = get_strategy(bot.strategy).resolve_params(params)
    if body.interval is not None and body.interval != bot.interval:
        bot.interval = body.interval
        bot.last_candle_time = None
    if body.risk is not None:
        bot.risk = body.risk.model_dump()
    add_event(db, bot.id, "info", "Configuração atualizada.")
    db.commit()
    return bot_summary(db, bot)


@router.delete("/{bot_id}")
def delete_bot(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    if manager.is_running(bot.id) or bot.status == "running":
        raise HTTPException(400, "Pare o bot antes de excluir.")
    if bot.mode == "live" and db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open")):
        raise HTTPException(400, "Este bot tem uma posição real aberta. Encerre a posição antes de excluir.")
    db.delete(bot)
    db.commit()
    return {"ok": True}


@router.post("/{bot_id}/start")
def start_bot(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    _require_live_ready(db, bot)
    bot.status = "running"
    bot.status_reason = ""
    bot.last_error = ""
    db.commit()
    manager.start_bot(bot.id)
    return bot_summary(db, bot)


@router.post("/{bot_id}/stop")
def stop_bot(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    bot.status = "stopped"
    bot.status_reason = ""
    db.commit()
    manager.stop_bot(bot.id)
    return bot_summary(db, bot)


@router.post("/{bot_id}/close-position")
def close_position(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    with manager.bot_lock(bot.id):
        db.refresh(bot)
        pos = db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open"))
        if pos is None:
            raise HTTPException(400, "Não há posição aberta.")
        market = manager.market_for(db, bot)
        risk = RiskConfig(**(bot.risk or {}))
        trader = PaperTrader(market, risk.fee_pct) if bot.mode == "paper" else make_live_trader(db, bot)
        service = BotService(db, bot, market, trader)
        try:
            service.sell(pos, 1.0, "manual")
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(400, f"Falha ao vender: {exc}") from exc
    return bot_summary(db, bot)


@router.post("/{bot_id}/reset-paper")
def reset_paper(bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    if bot.mode != "paper":
        raise HTTPException(400, "Só bots simulados podem ser resetados.")
    if bot.status == "running":
        raise HTTPException(400, "Pare o bot antes de resetar.")
    db.execute(delete(Order).where(Order.bot_id == bot.id))
    db.execute(delete(Position).where(Position.bot_id == bot.id))
    db.execute(delete(BotEvent).where(BotEvent.bot_id == bot.id))
    bot.paper_balance = bot.paper_initial_balance
    bot.last_candle_time = None
    bot.last_signal = None
    bot.total_runtime_seconds = 0.0
    add_event(db, bot.id, "info", "Simulação resetada.")
    db.commit()
    return bot_summary(db, bot)


@router.get("/{bot_id}/positions")
def positions(
    status: str | None = Query(None, pattern="^(open|closed)$"),
    limit: int = Query(100, ge=1, le=1000),
    bot: Bot = Depends(get_user_bot),
    db: Session = Depends(get_db),
):
    q = select(Position).where(Position.bot_id == bot.id)
    if status:
        q = q.where(Position.status == status)
    price = price_for(db, bot)
    fee = RiskConfig(**(bot.risk or {})).fee_pct
    return [position_view(p, price, fee) for p in db.scalars(q.order_by(Position.id.desc()).limit(limit))]


@router.get("/{bot_id}/orders")
def orders(limit: int = Query(100, ge=1, le=1000), bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    rows = db.scalars(select(Order).where(Order.bot_id == bot.id).order_by(Order.id.desc()).limit(limit))
    return [
        {
            "id": o.id,
            "position_id": o.position_id,
            "side": o.side,
            "price": o.price,
            "qty": o.qty,
            "quote_qty": o.quote_qty,
            "fee_quote": o.fee_quote,
            "reason": o.reason,
            "status": o.status,
            "exchange_order_id": o.exchange_order_id,
            "mode": o.mode,
            "created_at": o.created_at.isoformat(),
        }
        for o in rows
    ]


@router.get("/{bot_id}/events")
def events(
    limit: int = Query(100, ge=1, le=500),
    level: str | None = None,
    bot: Bot = Depends(get_user_bot),
    db: Session = Depends(get_db),
):
    q = select(BotEvent).where(BotEvent.bot_id == bot.id)
    if level:
        q = q.where(BotEvent.level.in_(level.split(",")))
    rows = db.scalars(q.order_by(BotEvent.id.desc()).limit(limit))
    return [
        {"id": e.id, "level": e.level, "message": e.message, "data": e.data, "created_at": e.created_at.isoformat()}
        for e in rows
    ]


@router.get("/{bot_id}/chart")
def chart(limit: int = Query(300, ge=50, le=1000), bot: Bot = Depends(get_user_bot), db: Session = Depends(get_db)):
    strategy = get_strategy(bot.strategy)
    params = strategy.resolve_params(bot.strategy_params)
    market = manager.market_for(db, bot)
    try:
        df = market.klines(bot.symbol, bot.interval, limit=limit + strategy.warmup(params), closed_only=False)
    except Exception as exc:
        raise HTTPException(502, f"Binance indisponível: {exc}") from exc
    out = strategy.run(df, params)
    view = df.tail(limit)
    idx = view.index
    last_closed = -2 if int(df["close_time"].iloc[-1]) >= now_ms() else -1

    step = interval_ms(bot.interval)
    first_ms = int(view["time"].iloc[0])
    markers = []
    for o in db.scalars(select(Order).where(Order.bot_id == bot.id).order_by(Order.id)):
        t = int(o.created_at.timestamp() * 1000)
        if t < first_ms:
            continue
        markers.append(
            {"time": (t // step) * step // 1000, "side": o.side, "price": o.price, "reason": o.reason, "qty": o.qty}
        )

    pos = db.scalar(select(Position).where(Position.bot_id == bot.id, Position.status == "open"))
    lines = []
    if pos:
        risk = RiskConfig(**(bot.risk or {}))
        lines.append({"label": "Entrada", "price": pos.entry_price, "kind": "entry"})
        if pos.stop_price:
            lines.append({"label": {"trailing_stop": "Trailing", "breakeven": "Break-even"}.get(pos.stop_kind, "Stop"), "price": pos.stop_price, "kind": "stop"})
        for i, tp in enumerate(risk.take_profits):
            if i >= pos.tp_index:
                lines.append({"label": f"Alvo {tp.pct:g}%".replace(".", ","), "price": pos.entry_price * (1 + tp.pct / 100), "kind": "target"})

    return {
        "candles": [
            {"time": int(r.time) // 1000, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume}
            for r in view.itertuples()
        ],
        "overlays": {
            name: [{"time": int(t) // 1000, "value": float(v)} for t, v in zip(view["time"], s.loc[idx]) if v == v]
            for name, s in out.overlays.items()
        },
        "markers": markers,
        "lines": lines,
        "preview": {**out.snapshot(last_closed), "candle_time": int(df["time"].iloc[last_closed])},
    }
