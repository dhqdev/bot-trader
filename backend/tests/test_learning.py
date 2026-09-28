"""Aprendizado da IA: guarda o que o teste prometia, confere depois e passa a pesar a escolha."""

from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.exchange import interval_ms
from app.db import session_scope
from app.models import LearningSample, User, utcnow
from app.security import hash_password
from app.services import backtesting, learning

from .conftest import make_ohlcv


@pytest.fixture
def user_id():
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "learning@test.dev"))
        if user is None:
            user = User(email="learning@test.dev", name="Aprendizado", password_hash=hash_password("x" * 8))
            db.add(user)
            db.flush()
        db.execute(delete(LearningSample).where(LearningSample.user_id == user.id))
        return user.id


def _row(symbol: str, key: str, ret: float = 20.0, recent: float = 5.0, level: str = "baixa", trades: int = 12) -> dict:
    return {"symbol": symbol, "level": level, "key": key, "return_pct": ret, "recent_return_pct": recent, "drawdown_pct": -10.0,
            "trades": trades, "score": ret - 5 + 0.5 * (recent - 5), "days": 730 if level == "baixa" else 365,
            "eligible": trades >= 4, "fee_pct": 0.4}  # fmt: skip


def test_forward_result_only_uses_the_period_after_the_prediction(monkeypatch):
    df = make_ohlcv(3000, interval="4h")
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: df)
    config = learning._config("baixa", "squeeze:4h", 0.4)
    snapshot = int(df["time"].iloc[2000])
    first = learning.forward_result("SOLUSDT", config, snapshot, 60)
    assert first["days"] == 60 and set(first) >= {"return_pct", "trades", "buy_hold_pct"}

    later = df.copy()
    later.loc[2361:, ["open", "high", "low", "close"]] *= 3  # o que vem depois do horizonte não muda a conferência
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: later)
    assert learning.forward_result("SOLUSDT", config, snapshot, 60) == first

    with pytest.raises(ValueError):  # horizonte ainda não terminou: não dá para conferir
        learning.forward_result("SOLUSDT", config, int(df["time"].iloc[-10]), 60)


def test_calibration_rewards_what_delivers_and_blocks_what_does_not(user_id):
    step = interval_ms("4h")
    with session_scope() as db:
        for i in range(100):  # prometia +60% em 2 anos e perdeu 6% em cada 60 dias
            db.add(LearningSample(user_id=user_id, symbol="SOLUSDT", level="baixa", key="squeeze:4h", config={}, snapshot_ms=i * step,
                                  test={"approved": True, "return_pct": 60.0, "days": 730}, horizon_days=60, status="done",
                                  forward={"return_pct": -6.0, "days": 60}))  # fmt: skip
        for i in range(10):  # prometia +20% em 1 ano e entregou +3% em 30 dias
            db.add(LearningSample(user_id=user_id, symbol="SOLUSDT", level="media", key="ignition:1h", config={}, snapshot_ms=i * step,
                                  test={"approved": True, "return_pct": 20.0, "days": 365}, horizon_days=30, status="done",
                                  forward={"return_pct": 3.0, "days": 30}))  # fmt: skip
        db.add(LearningSample(user_id=user_id, symbol="SOLUSDT", level="media", key="hilo_rsi:2h", config={}, snapshot_ms=0,
                              test={"approved": False, "return_pct": -5.0, "days": 365}, horizon_days=30, status="done",
                              forward={"return_pct": -50.0, "days": 30}))  # reprovado no teste: não conta  # fmt: skip
    cal = learning.calibration(user_id)
    assert set(cal) == {"squeeze:4h", "ignition:1h"}
    assert cal["squeeze:4h"]["samples"] == 100 and cal["squeeze:4h"]["factor"] < learning.BLOCK_FACTOR and cal["squeeze:4h"]["hit_rate"] == 0
    assert cal["ignition:1h"]["factor"] > 1 and cal["ignition:1h"]["hit_rate"] == 100

    rows = [{**_row("SOLUSDT", "squeeze:4h"), "approved": True, "yearly_score": 30.0},
            {**_row("SOLUSDT", "ignition:1h", level="media"), "approved": True, "yearly_score": 10.0}]  # fmt: skip
    learning.apply(rows, cal)
    squeeze = next(r for r in rows if r["key"] == "squeeze:4h")
    ignition = next(r for r in rows if r["key"] == "ignition:1h")
    assert squeeze["approved"] is False and squeeze["learned_block"] is True  # promete e não entrega: sai da escolha
    assert ignition["yearly_score"] == pytest.approx(10.0 * cal["ignition:1h"]["factor"]) and rows[0] is ignition

    with session_scope() as db:
        s = learning.summary(db, user_id)
    assert s["checked"] == 111 and [t["key"] for t in s["table"]][0] == "squeeze:4h" and s["table"][0]["blocked"] is True


def test_one_prediction_per_week_and_evaluation(user_id, monkeypatch):
    rows = [{**_row("SOLUSDT", "squeeze:4h"), "approved": True}]
    with session_scope() as db:
        assert learning.record(db, user_id, rows) == 1
    with session_scope() as db:
        assert learning.record(db, user_id, rows) == 0  # a mesma moeda e robô só de novo na semana que vem
        sample = db.scalar(select(LearningSample).where(LearningSample.user_id == user_id))
        assert sample.status == "pending" and sample.test["approved"] is True and sample.config["risk"]["fee_pct"] == 0.4
        sample.snapshot_ms -= 61 * 86_400_000  # o horizonte de 60 dias já passou
    monkeypatch.setattr(learning, "forward_result", lambda symbol, config, snapshot, horizon: {"return_pct": 4.0, "trades": 2, "days": horizon})
    assert learning.evaluate_due(user_id) == 1
    with session_scope() as db:
        sample = db.scalar(select(LearningSample).where(LearningSample.user_id == user_id))
        assert sample.status == "done" and sample.forward["return_pct"] == 4.0


def test_learns_from_history_only_once(user_id, monkeypatch):
    calls = []
    monkeypatch.setattr(learning, "backfill", lambda uid: calls.append(("history", uid)) or 0)
    monkeypatch.setattr(learning, "lab_scan", lambda uid: calls.append(("week", uid)) or 0)
    monkeypatch.setattr(learning, "evaluate_due", lambda uid: calls.append(("check", uid)) or 0)
    with session_scope() as db:
        others = [u for u in db.scalars(select(User.id)) if u != user_id]
    learning.tick()
    assert ("history", user_id) in calls and ("week", user_id) in calls and ("check", user_id) in calls

    with session_scope() as db:
        for source in ("history", "live"):
            db.add(LearningSample(user_id=user_id, symbol="SOLUSDT", level="baixa", key="squeeze:4h", config={}, test={}, snapshot_ms=0,
                                  horizon_days=60, source=source, created_at=utcnow() - timedelta(hours=1)))  # fmt: skip
    calls.clear()
    learning.tick()
    assert [c for c in calls if c[1] == user_id] == [("check", user_id)]  # histórico já aprendido e previsões da semana já guardadas
    assert all(c[1] in others for c in calls if c[1] != user_id)
