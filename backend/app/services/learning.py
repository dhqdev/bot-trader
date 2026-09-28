"""A inteligência que vai melhorando: a IA guarda o que cada estratégia prometia e confere depois.

Toda semana, nas moedas mais negociadas (e liberadas na conta), ela anota o
resultado do teste de cada robô das volatilidades baixa e média (uma "previsão").
Passado o horizonte (30 dias em 1h e 2h, 60 em 4h e 120 no diário), mede o que o robô fez nesse
período novo, com os candles reais que chegaram depois: um teste no futuro, que
não dá para "decorar". Para não começar do zero, faz o mesmo em datas passadas.

Com isso calcula, por estratégia e tempo de candle, quanto do prometido foi
entregue. O modo automático usa esse peso na escolha: quem cumpre ganha peso;
quem promete e não entrega perde e, com amostra suficiente, deixa de ser escolhido.
Nada disso chama o GPT: é conta com os dados do mercado.
"""

import logging
import threading
import time
from datetime import timedelta

import numpy as np
from sqlalchemy import select

from app.core.backtest import run_backtest
from app.core.exchange import INTERVAL_MINUTES, interval_ms, now_ms
from app.core.markets import get_market
from app.core.risk import RiskConfig
from app.core.sentiment import sentiment
from app.core.strategies import get_strategy
from app.db import session_scope
from app.models import LearningSample, User, utcnow
from app.services import backtesting, fees, ranking, tradable

log = logging.getLogger("bot_trader.learning")

LEVELS = ("baixa", "media")
HORIZON_DAYS = {"1h": 30, "2h": 30, "4h": 60, "1d": 120}  # robôs lentos precisam de mais tempo para operar
SPACING = timedelta(days=7)  # no máximo uma previsão por semana para cada moeda e robô
COINS = 8
HISTORY_CUTOFFS = {"baixa": (60, 120, 180, 240), "media": (30, 60, 90, 120, 150, 180)}  # dias atrás
SHRINK_SAMPLES = 30  # com 30 previsões conferidas, o que aconteceu de verdade pesa metade
MIN_FACTOR, MAX_FACTOR = 0.3, 1.5
BLOCK_FACTOR = 0.5  # abaixo disso, com amostra suficiente, a estratégia deixa de ser escolhida
STABILIZER = 1.0  # % em 30 dias: evita dividir por promessas minúsculas

_run_lock = threading.Lock()


def _per_30(pct: float, days: float) -> float:
    return pct * 30 / days if days else 0.0


def _config(level: str, key: str, fee_pct: float | None) -> dict | None:
    robot = ranking.find_robot(level, key)
    if robot is None:
        return None
    risk = {**robot["risk"], **({} if fee_pct is None else {"fee_pct": fee_pct})}
    return {"strategy": robot["strategy"], "interval": robot["interval"], "params": robot["params"], "risk": RiskConfig(**risk).model_dump()}


def _last_closed_open(interval: str) -> int:
    step = interval_ms(interval)
    return (now_ms() // step) * step - step


# ---------------------------------------------------------------------------
# Guardar previsões


def record(db, user_id: int, rows: list[dict], source: str = "live", snapshot_ms: int | None = None) -> int:
    """Guarda uma previsão por linha do teste (formato de autotrade.scan). Devolve quantas guardou."""
    from app.services.autotrade import approved  # evita import circular

    since = utcnow() - SPACING
    recent = set()
    if source == "live":
        recent = {
            (s, k)
            for s, k in db.execute(
                select(LearningSample.symbol, LearningSample.key).where(
                    LearningSample.user_id == user_id, LearningSample.source == "live", LearningSample.created_at >= since
                )
            )
        }
    saved = 0
    for r in rows:
        if (r["symbol"], r["key"]) in recent:
            continue
        config = _config(r["level"], r["key"], r.get("fee_pct"))
        if config is None:
            continue
        test = {k: r[k] for k in ("return_pct", "recent_return_pct", "drawdown_pct", "trades", "score", "days")}
        test["approved"] = approved(r)
        db.add(LearningSample(
            user_id=user_id, symbol=r["symbol"], level=r["level"], key=r["key"], config=config, test=test,
            snapshot_ms=snapshot_ms if snapshot_ms is not None else _last_closed_open(config["interval"]),
            horizon_days=HORIZON_DAYS[config["interval"]], source=source, status="pending",
        ))  # fmt: skip
        saved += 1
    return saved


# ---------------------------------------------------------------------------
# Conferir o que aconteceu


def forward_result(symbol: str, config: dict, snapshot_ms: int, horizon_days: int) -> dict:
    """O que o robô fez no período seguinte à previsão (só candles depois dela)."""
    interval = config["interval"]
    strategy = get_strategy(config["strategy"])
    params = strategy.resolve_params(config["params"])
    step = interval_ms(interval)
    warm = max(strategy.warmup(params) // 2, 30)
    horizon_bars = int(horizon_days * 1440 / INTERVAL_MINUTES[interval])
    df = backtesting.history(symbol, interval, warm + max(0, (now_ms() - snapshot_ms) // step) + 5)
    times = df["time"].to_numpy(dtype="int64")
    start = int(np.searchsorted(times, snapshot_ms, side="right"))  # primeiro candle depois da previsão
    end = int(np.searchsorted(times, snapshot_ms + horizon_bars * step, side="right"))
    if start < warm or end - start < horizon_bars * 0.8:
        raise ValueError("histórico insuficiente para conferir a previsão")
    sub = df.iloc[:end].reset_index(drop=True)
    try:
        sent = sentiment.aligned(sub)
    except Exception:
        sent = None
    risk = RiskConfig(**{**config["risk"], "sizing_mode": "percent_balance", "balance_percent": 100})
    m = run_backtest(sub, strategy.key, params, risk, interval, 1000.0, max_curve_points=2, sentiment=sent, start_index=start)["metrics"]
    return {"return_pct": m["total_return_pct"], "trades": m["trades"], "drawdown_pct": m["max_drawdown_pct"],
            "buy_hold_pct": m["buy_hold_return_pct"], "days": horizon_days}  # fmt: skip


def evaluate_due(user_id: int, limit: int = 3000) -> int:
    """Confere as previsões cujo horizonte já passou. Devolve quantas conferiu."""
    now = now_ms()
    with session_scope() as db:
        due = [
            (s.id, s.symbol, s.config, s.snapshot_ms, s.horizon_days)
            for s in db.scalars(
                select(LearningSample).where(LearningSample.user_id == user_id, LearningSample.status == "pending").order_by(LearningSample.snapshot_ms).limit(limit * 3)
            )
            if s.snapshot_ms + s.horizon_days * 86_400_000 <= now
        ][:limit]
    done = 0
    for sample_id, symbol, config, snapshot_ms, horizon in due:
        try:
            result, status = forward_result(symbol, config, snapshot_ms, horizon), "done"
        except Exception as exc:
            log.info("Previsão %s não conferida: %s", sample_id, exc)
            result, status = {"error": str(exc)[:200]}, "failed"
        with session_scope() as db:
            sample = db.get(LearningSample, sample_id)
            if sample is not None:
                sample.forward, sample.status, sample.evaluated_at = result, status, utcnow()
        done += status == "done"
        time.sleep(0.01)  # deixa o resto do sistema respirar
    return done


# ---------------------------------------------------------------------------
# O que foi aprendido


def calibration(user_id: int) -> dict[str, dict]:
    """Por estratégia e tempo de candle: quanto das previsões aprovadas se cumpriu depois."""
    with session_scope() as db:
        rows = [
            (s.key, s.test, s.forward)
            for s in db.scalars(select(LearningSample).where(LearningSample.user_id == user_id, LearningSample.status == "done"))
        ]
    groups: dict[str, list[tuple[float, float]]] = {}
    for key, test, fwd in rows:
        if not test.get("approved") or not fwd or "return_pct" not in fwd:
            continue
        promised = _per_30(test["return_pct"], test.get("days") or 365)
        delivered = _per_30(fwd["return_pct"], fwd.get("days") or 30)
        groups.setdefault(key, []).append((promised, delivered))
    out = {}
    for key, pairs in groups.items():
        n = len(pairs)
        promised = float(np.mean([p for p, _ in pairs]))
        delivered = float(np.mean([d for _, d in pairs]))
        raw = (delivered + STABILIZER) / (promised + STABILIZER) if promised + STABILIZER > 0 else 1.0
        raw = min(MAX_FACTOR, max(MIN_FACTOR, raw))
        weight = n / (n + SHRINK_SAMPLES)
        out[key] = {
            "samples": n,
            "promised_30d": round(promised, 2),
            "delivered_30d": round(delivered, 2),
            "hit_rate": round(sum(d > 0 for _, d in pairs) / n * 100),
            "factor": round(1 + weight * (raw - 1), 3),
        }
    return out


def apply(rows: list[dict], cal: dict[str, dict]) -> None:
    """Ajusta a nota de cada robô pelo que a IA aprendeu; com amostra suficiente, quem não entrega sai da escolha."""
    for r in rows:
        learned = cal.get(r["key"])
        factor = learned["factor"] if learned else 1.0
        r["learned_factor"] = factor
        r["yearly_score"] = round(r["yearly_score"] * factor, 2) if r["yearly_score"] > 0 else r["yearly_score"]
        if learned and learned["samples"] >= SHRINK_SAMPLES and factor < BLOCK_FACTOR:
            r["approved"] = False
            r["learned_block"] = True
    rows.sort(key=lambda r: (not r["approved"], -r["yearly_score"]))


def summary(db, user_id: int) -> dict:
    samples = list(db.execute(select(LearningSample.status, LearningSample.source, LearningSample.snapshot_ms, LearningSample.horizon_days)
                              .where(LearningSample.user_id == user_id)))  # fmt: skip
    pending = [s for s in samples if s.status == "pending"]
    next_ms = min((s.snapshot_ms + s.horizon_days * 86_400_000 for s in pending), default=None)
    cal = calibration(user_id)
    table = []
    for key, c in sorted(cal.items(), key=lambda kv: -kv[1]["samples"]):
        strategy, interval = key.split(":")
        table.append({"key": key, "name": ranking.robot_config(strategy, interval)["name"], **c,
                      "blocked": c["samples"] >= SHRINK_SAMPLES and c["factor"] < BLOCK_FACTOR})  # fmt: skip
    return {
        "samples": len(samples),
        "checked": sum(s.status == "done" for s in samples),
        "pending": len(pending),
        "from_history": sum(s.source == "history" and s.status == "done" for s in samples),
        "next_check_at": next_ms,
        "table": table,
        "limits": {"shrink_samples": SHRINK_SAMPLES, "block_factor": BLOCK_FACTOR},
    }


# ---------------------------------------------------------------------------
# Rotina (agendador)


def _top_coins(user_id: int) -> list[str]:
    allowed = tradable.account_symbols(user_id)
    tickers = get_market().tickers()
    if allowed is not None:
        tickers = {s: t for s, t in tickers.items() if s in allowed}
    return [s for s, _ in ranking.liquid_coins(tickers, COINS)]


def lab_scan(user_id: int) -> int:
    """Previsões da semana, mesmo com o modo automático desligado (a IA aprende o tempo todo)."""
    from app.services.autotrade import scan  # evita import circular

    symbols = _top_coins(user_id)
    rows, _ = scan(symbols, {s: fees.account_fee_pct(user_id, s) for s in symbols})
    with session_scope() as db:
        return record(db, user_id, rows)


def _test_at(df, sent, config: dict, start: int, end: int) -> dict:
    """Resultado do teste como o ranking faria, usando só os candles até `end`."""
    risk = RiskConfig(**{**config["risk"], "sizing_mode": "percent_balance", "balance_percent": 100})
    sub = df.iloc[:end].reset_index(drop=True)
    s = (sent[0][:end], sent[1][:end]) if sent is not None else None
    full = run_backtest(sub, config["strategy"], config["params"], risk, config["interval"], 1000.0, max_curve_points=2, sentiment=s, start_index=start)["metrics"]
    split = start + (end - start) * 2 // 3
    recent = run_backtest(sub, config["strategy"], config["params"], risk, config["interval"], 1000.0, max_curve_points=2, sentiment=s, start_index=split)["metrics"]
    score = (full["total_return_pct"] + 0.5 * full["max_drawdown_pct"]) + 0.5 * (recent["total_return_pct"] + 0.5 * recent["max_drawdown_pct"])
    return {"return_pct": full["total_return_pct"], "recent_return_pct": recent["total_return_pct"], "drawdown_pct": full["max_drawdown_pct"],
            "trades": full["trades"], "score": round(score, 2), "eligible": full["trades"] >= ranking.MIN_TRADES}  # fmt: skip


def backfill(user_id: int) -> int:
    """Aprende com o histórico: previsões em datas passadas, conferidas com o que veio depois."""
    saved = 0
    for symbol in _top_coins(user_id):
        fee = fees.account_fee_pct(user_id, symbol)
        for level in LEVELS:
            info = ranking.LEVELS[level]
            for interval in info["intervals"]:
                robots = [r for r in ranking.catalog(level) if r["interval"] == interval]
                warm = max(max(get_strategy(r["strategy"]).warmup(r["params"]) // 2, 30) for r in robots)
                window = int(info["days"] * 1440 / INTERVAL_MINUTES[interval])
                oldest = max(HISTORY_CUTOFFS[level]) * 1440 // INTERVAL_MINUTES[interval]
                try:
                    df = backtesting.history(symbol, interval, warm + window + oldest)
                except Exception as exc:
                    log.info("Sem histórico de %s %s para aprender: %s", symbol, interval, exc)
                    continue
                try:
                    sent = sentiment.aligned(df)
                except Exception:
                    sent = None
                for days_ago in HISTORY_CUTOFFS[level]:
                    end = len(df) - days_ago * 1440 // INTERVAL_MINUTES[interval]
                    start = end - window
                    if start < warm:
                        continue
                    rows = []
                    for robot in robots:
                        config = _config(level, robot["key"], fee)
                        test = _test_at(df, sent, config, start, end)
                        rows.append({**test, "symbol": symbol, "level": level, "key": robot["key"], "days": info["days"], "fee_pct": fee})
                    with session_scope() as db:
                        saved += record(db, user_id, rows, source="history", snapshot_ms=int(df["time"].iloc[end - 1]))
                    time.sleep(0.05)  # deixa o resto do sistema respirar
    return saved


def tick() -> None:
    """Uma volta: aprende com o histórico (só na primeira vez), guarda as previsões da semana e confere as vencidas."""
    if not _run_lock.acquire(blocking=False):
        return
    try:
        with session_scope() as db:
            users = list(db.scalars(select(User.id)))
        for user_id in users:
            with session_scope() as db:
                has_history = db.scalar(select(LearningSample.id).where(LearningSample.user_id == user_id, LearningSample.source == "history").limit(1))
                recent_live = db.scalar(
                    select(LearningSample.id).where(LearningSample.user_id == user_id, LearningSample.source == "live",
                                                    LearningSample.created_at >= utcnow() - SPACING).limit(1)
                )  # fmt: skip
            try:
                if has_history is None:
                    log.info("Aprendendo com o histórico: %s previsões", backfill(user_id))
                if recent_live is None:
                    log.info("Previsões da semana guardadas: %s", lab_scan(user_id))
                checked = evaluate_due(user_id)
                if checked:
                    log.info("Previsões conferidas: %s", checked)
            except Exception as exc:
                log.warning("Aprendizado falhou: %s", exc)
    finally:
        _run_lock.release()
