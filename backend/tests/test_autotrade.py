"""Modo automático: a IA escolhe, liga, acompanha e troca os robôs sozinha."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api import autotrade as auto_api
from app.api import bots as bots_api
from app.core.engine import BotService, manager
from app.core.exchange import SymbolRules
from app.db import session_scope
from app.main import app
from app.models import AutopilotConfig, AutoCycle, AutoRobot, AutoTrader, Bot, Position, User, utcnow
from app.services import autotrade, fees, ranking
from app.services.llm import AIConfig

from .conftest import FakeMarket

EMAIL, PASSWORD = "auto@test.dev", "senha-auto-1"
AI = AIConfig("anthropic", "sk-test", "claude-opus-5", "claude-haiku-4-5")


class AutoMarket(FakeMarket):
    def tickers(self):
        return {
            "BTCUSDT": {"price": 84000.0, "change_pct": 1.0, "quote_volume": 9e8},
            "ETHUSDT": {"price": 3000.0, "change_pct": 1.0, "quote_volume": 5e8},
            "SOLUSDT": {"price": 120.0, "change_pct": -2.0, "quote_volume": 3e8},
            "XRPUSDT": {"price": 2.5, "change_pct": 0.5, "quote_volume": 2e8},
            "USDCUSDT": {"price": 1.0, "change_pct": 0.0, "quote_volume": 5e9},  # estável: nunca vira robô
        }

    def symbol_rules(self, symbol):
        return SymbolRules(symbol, symbol[:-4], "USDT", tick_size=0.01, step_size=0.001, min_qty=0.001, min_notional=1.0)


def row(key: str, ret: float, recent: float, dd: float = -10.0, trades: int = 12) -> dict:
    strategy, interval = key.split(":")
    score = round(ret + 0.5 * dd + 0.5 * (recent + 0.5 * dd), 2)
    return {"key": key, "name": key, "strategy": strategy, "interval": interval, "return_pct": ret, "recent_return_pct": recent,
            "drawdown_pct": dd, "trades": trades, "win_rate_pct": 50.0, "avg_trade_hours": 30.0, "buy_hold_pct": 10.0,
            "score": score, "eligible": trades >= ranking.MIN_TRADES}  # fmt: skip


# pontuação por ano: BTC squeeze 13,75 > ETH squeeze 10,75 > BTC ignition 9,5 > BTC confluence 7,5
TABLE = {
    ("BTCUSDT", "baixa"): [row("squeeze:4h", 30, 10), row("confluence:1d", 20, 5)],
    ("BTCUSDT", "media"): [row("ignition:1h", 15, 4)],
    ("ETHUSDT", "baixa"): [row("squeeze:4h", 25, 8)],
    ("SOLUSDT", "baixa"): [row("donchian_breakout:4h", -5, -2)],  # prejuízo: reprovado
    ("SOLUSDT", "media"): [row("ignition:1h", 10, -1)],  # perdeu no período recente: reprovado
    ("XRPUSDT", "baixa"): [row("hilo_rsi:4h", 12, 3, trades=2)],  # poucas operações: reprovado
}


@pytest.fixture
def rank_calls():
    return []


@pytest.fixture
def table(monkeypatch, rank_calls):
    data = {k: [dict(r) for r in v] for k, v in TABLE.items()}

    def rank(symbol, level, force=False, fee_pct=None):
        rank_calls.append((symbol, level, fee_pct))
        if (symbol, level) not in data:
            raise ValueError(f"Sem histórico suficiente de {symbol}.")
        return {"symbol": symbol, "level": level, "days": ranking.LEVELS[level]["days"], "robots": data[(symbol, level)]}

    monkeypatch.setattr(ranking, "rank", rank)
    return data


@pytest.fixture(autouse=True)
def offline(monkeypatch, table):
    market = AutoMarket()
    monkeypatch.setattr(autotrade, "get_market", lambda *a, **k: market)
    monkeypatch.setattr(bots_api, "get_market", lambda *a, **k: market)
    monkeypatch.setattr(manager, "market_factory", lambda db, bot: market)
    monkeypatch.setattr(manager, "spawn", lambda bot_id: None)
    monkeypatch.setattr("app.services.stats.prices.get", lambda symbol, *a, **k: market.current)
    monkeypatch.setattr(auto_api, "resolve_ai", lambda user_id: None)
    monkeypatch.setattr(autotrade, "_ai_for", lambda user_id: None)
    monkeypatch.setattr(autotrade, "launch", lambda cycle_id, ai: autotrade.execute(cycle_id, ai))
    monkeypatch.setattr(fees, "account_fee_pct", lambda user_id, symbol: None)  # sem chave da OKX: taxa padrão
    yield market


@pytest.fixture(scope="module")
def api(fresh_db):
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
        yield c


@pytest.fixture(autouse=True)
def clean(api):
    with session_scope() as db:
        for model in (AutoCycle, AutoRobot, AutoTrader, Bot):
            db.execute(delete(model))
    yield


def _uid() -> int:
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.email == EMAIL))


def _robots(state: str | None = None) -> list[tuple[AutoRobot, Bot]]:
    with session_scope() as db:
        return autotrade.managed(db, _uid(), [state] if state else None)


def _bot_by_symbol(symbol: str, state: str = "active") -> Bot:
    return next(bot for ar, bot in _robots(state) if bot.symbol == symbol)


def _add_position(bot: Bot, pnl: float | None, status: str = "closed", price: float = 100.0, cost: float = 300.0) -> None:
    """Operação fechada com o resultado dado, ou posição aberta comprada ao preço atual (sem lucro nem perda)."""
    closed = status == "closed"
    with session_scope() as db:
        now = utcnow()
        db.add(Position(bot_id=bot.id, symbol=bot.symbol, mode=bot.mode, strategy=bot.strategy, status=status, entry_price=price,
                        entry_time=now - timedelta(hours=5), initial_qty=cost / price, qty=0.0 if closed else cost / price, cost_quote=cost,
                        proceeds_quote=cost + (pnl or 0) if closed else 0.0, highest_price=price,
                        exit_time=now if closed else None, pnl_quote=pnl, exit_reason="stop_loss" if closed else ""))  # fmt: skip


def test_turning_on_picks_diversified_approved_robots(api):
    data = api.post("/api/auto/start", json={}).json()
    cfg = data["config"]
    assert cfg["enabled"] and cfg["mode"] == "paper" and cfg["budget"] == 1000 and cfg["slots"] == 3
    assert cfg["allocation"] == pytest.approx(333.33)

    robots = _robots("active")
    picks = sorted(f"{bot.symbol}|{bot.strategy}:{bot.interval}" for _, bot in robots)
    # só aprovados, um por moeda: o 2º robô de BTC não entra; SOL e XRP foram reprovados; USDC nunca é testada
    assert picks == ["BTCUSDT|squeeze:4h", "ETHUSDT|squeeze:4h"]
    for ar, bot in robots:
        assert bot.status == "running" and bot.mode == "paper" and bot.name.endswith("(IA)")
        assert bot.risk["order_size_quote"] == pytest.approx(333.33) and bot.paper_initial_balance == pytest.approx(333.33)
        assert ar.expected["return_pct"] > 0 and "melhor equilíbrio" in ar.reason
        with session_scope() as db:
            assert db.get(AutopilotConfig, bot.id).allow_strategy_change is False  # trocar de estratégia é com o modo automático

    cycle = data["cycles"][0]
    assert cycle["status"] == "done" and [a["type"] for a in cycle["actions"]] == ["create", "create"]
    assert "Liguei" in cycle["summary"] and "Não consegui testar 2" in cycle["summary"]  # ETH e XRP sem histórico de 1h/2h
    assert {p["pick"] for p in cycle["pool"]} == {"BTCUSDT|squeeze:4h", "ETHUSDT|squeeze:4h", "BTCUSDT|ignition:1h", "BTCUSDT|confluence:1d"}
    assert data["performance"]["active_robots"] == 2 and data["running"] is False
    assert api.post("/api/auto/start", json={"budget": 4}).status_code == 422  # menos de 5 USDT não dá nem um robô


def test_simulation_uses_the_chosen_amount(api):
    cfg = api.post("/api/auto/start", json={"mode": "paper", "budget": 9.39}).json()["config"]
    assert cfg["mode"] == "paper" and cfg["budget"] == 9.39 and cfg["slots"] == 1
    [(ar, bot)] = _robots("active")  # com 9,39 USDT cabe um robô só, com tudo
    assert bot.mode == "paper" and ar.allocation == 9.39
    assert bot.paper_initial_balance == 9.39 and bot.risk["order_size_quote"] == 9.39


def test_small_budgets_use_fewer_robots():
    def split(budget: float) -> tuple[int, float]:
        cfg = AutoTrader(budget=budget, max_robots=autotrade.MAX_ROBOTS)
        return autotrade.slots(cfg), autotrade.allocation(cfg)

    assert split(9.0) == (1, 9.0)  # ~50 reais: um robô só, com tudo
    assert split(10.0) == (2, 5.0)
    assert split(1000.0) == (3, 333.33)


def test_tests_and_robots_use_the_real_account_fee(api, monkeypatch, rank_calls):
    monkeypatch.setattr(fees, "account_fee_pct", lambda user_id, symbol: 0.4)  # conta do Brasil no nível Lv1
    cycle = api.post("/api/auto/start", json={}).json()["cycles"][0]
    assert rank_calls and {fee for _, _, fee in rank_calls} == {0.4}
    assert "taxa real da sua conta na OKX: 0,40% por ordem" in cycle["summary"]
    robots = _robots("active")
    assert robots and all(bot.risk["fee_pct"] == 0.4 and ar.expected["fee_pct"] == 0.4 for ar, bot in robots)


def test_few_trades_weigh_less_than_a_consistent_record(table):
    # +60% com 4 operações (pode ter sido sorte) contra +30% com 40 operações
    table[("BTCUSDT", "baixa")] = [row("squeeze:4h", 60, 20, trades=4), row("confluence:1d", 30, 10, trades=40)]
    rows, _ = autotrade.scan(["BTCUSDT"])
    assert [r["key"] for r in rows] == ["confluence:1d", "squeeze:4h", "ignition:1h"]
    assert autotrade.confidence(10) == 0.5 and autotrade.confidence(0) == 0.0


def test_robot_losing_too_much_is_replaced_by_another(api):
    api.post("/api/auto/start", json={})
    btc = _bot_by_symbol("BTCUSDT")
    _add_position(btc, -40.0)  # -12% dos 333,33 que recebeu

    assert autotrade.tick() == []  # próximo ciclo só daqui a 24 h
    with session_scope() as db:
        ar, bot = db.get(AutoRobot, btc.id), db.get(Bot, btc.id)
        assert ar.state == "retired" and "perdeu" in ar.retire_reason and bot.status == "stopped"

    cycle = api.post("/api/auto/run").json()["cycles"][0]
    by_type = {a["type"]: a for a in cycle["actions"]}
    assert by_type["keep"]["name"].startswith("ETH") and "ligado há menos de 3 dias" in by_type["keep"]["text"]
    new = _bot_by_symbol("BTCUSDT")
    # o mesmo robô que acabou de perder fica de fora por um tempo: entra o próximo aprovado de BTC
    assert (new.strategy, new.interval) == ("ignition", "1h")


def test_robot_that_stops_passing_tests_waits_for_position_to_close(api, table, offline):
    api.post("/api/auto/start", json={})
    eth = _bot_by_symbol("ETHUSDT")
    with session_scope() as db:
        db.get(AutoRobot, eth.id).created_at = utcnow() - timedelta(days=4)
    _add_position(eth, None, status="open", price=offline.current)
    table[("ETHUSDT", "baixa")] = [row("squeeze:4h", 25, -3)]

    cycle = api.post("/api/auto/run").json()["cycles"][0]
    retired = next(a for a in cycle["actions"] if a["type"] == "retire")
    assert retired["state"] == "retiring" and "deixou de passar nos testes" in retired["text"]
    assert not [a for a in cycle["actions"] if a["type"] == "create"]  # a posição aberta ainda ocupa a vaga de ETH

    with session_scope() as db:
        bot = db.get(Bot, eth.id)
        allowed, reason = BotService(db, bot, None, None).can_enter()
        assert bot.status == "running" and not allowed and "encerrando" in reason  # só vende, não compra de novo
        pos = db.scalar(select(Position).where(Position.bot_id == eth.id))
        pos.status, pos.exit_time, pos.pnl_quote = "closed", utcnow(), 5.0

    autotrade.tick()
    with session_scope() as db:
        assert db.get(AutoRobot, eth.id).state == "retired" and db.get(Bot, eth.id).status == "stopped"


def test_protection_pauses_everything_until_resumed(api):
    api.post("/api/auto/start", json={})
    _add_position(_bot_by_symbol("BTCUSDT"), -150.0)
    _add_position(_bot_by_symbol("ETHUSDT"), -60.0)  # total -210: passou de -20% de 1000

    autotrade.tick()
    data = api.get("/api/auto").json()
    assert "proteção" in data["config"]["paused_reason"] and data["performance"]["active_robots"] == 0
    assert data["performance"]["total_pnl"] == pytest.approx(-210.0)
    with session_scope() as db:
        db.get(AutoTrader, _uid()).next_run_at = utcnow() - timedelta(minutes=1)
    assert autotrade.tick() == []  # pausado: nenhum ciclo novo
    assert api.post("/api/auto/run").status_code == 400

    data = api.post("/api/auto/resume").json()
    assert data["config"]["paused_reason"] == ""
    # BTC e ETH squeeze acabaram de perder: quem entra é o próximo aprovado
    assert [f"{b.strategy}:{b.interval}" for _, b in _robots("active")] == ["ignition:1h"]
    assert api.post("/api/auto/resume").status_code == 400


def _ai_client(reply: dict | None, calls: list):
    def create(**kwargs):
        calls.append(kwargs)
        if reply is None:
            raise RuntimeError("sem créditos")
        return SimpleNamespace(stop_reason="end_turn", model=kwargs["model"], content=[SimpleNamespace(type="text", text=json.dumps(reply))])

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def _run_with_ai(reply: dict | None) -> tuple[dict, list]:
    uid, calls = _uid(), []
    with session_scope() as db:
        autotrade.enable(db, autotrade.get_config(db, uid), "paper", 1000.0)
        cycle_id = autotrade.start_cycle(db, uid, "manual").id
    autotrade.execute(cycle_id, AI, client=_ai_client(reply, calls))
    with session_scope() as db:
        return autotrade.cycle_view(db.get(AutoCycle, cycle_id)), calls


def test_ai_chooses_only_among_approved_robots(api):
    reply = {"summary": "Liguei só o de ETH: o mais estável.", "hold_cash": False, "retire": [{"bot_id": 999, "reason": "inventado"}],
             "picks": [{"pick": "SOLUSDT|donchian_breakout:4h", "reason": "reprovado"}, {"pick": "ETHUSDT|squeeze:4h", "reason": "consistente"}]}  # fmt: skip
    cycle, calls = _run_with_ai(reply)
    sent = calls[0]["messages"][0]["content"]
    assert '"aprovados_hoje"' in sent and "<noticias_recentes>" in sent and calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert "SOLUSDT|donchian_breakout:4h" not in sent  # reprovados nem chegam à IA
    assert cycle["summary"].startswith(reply["summary"]) and cycle["ai_model"] == "claude-opus-5"
    # a IA não inventa robô: o reprovado é ignorado e ela pode preferir menos robôs que vagas
    assert [(b.symbol, b.strategy, a.reason) for a, b in _robots("active")] == [("ETHUSDT", "squeeze", "consistente")]


def test_ai_can_keep_money_in_usdt(api):
    cycle, _ = _run_with_ai({"summary": "Mercado em pânico: fico em USDT.", "hold_cash": True, "retire": [], "picks": []})
    assert cycle["summary"].startswith("Mercado em pânico") and _robots("active") == []


def test_ai_failure_falls_back_to_the_ranking(api):
    cycle, calls = _run_with_ai(None)
    assert calls and len(_robots("active")) == 2
    assert "sem créditos" in cycle["summary"] and "regras do ranking" in cycle["summary"]


def test_stop_and_real_money_rules(api):
    assert api.post("/api/auto/run").status_code == 400  # desligado
    r = api.post("/api/auto/start", json={"mode": "live", "budget": 100, "password": PASSWORD})
    assert r.status_code == 400 and "OKX" in r.json()["detail"]

    api.post("/api/auto/start", json={})
    data = api.post("/api/auto/stop").json()
    assert data["config"]["enabled"] is False and data["performance"]["active_robots"] == 0
    assert all(ar.state == "retired" and bot.status == "stopped" for ar, bot in _robots())
