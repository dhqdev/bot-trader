"""Escolha de robô: ranking automático, recomendação (IA ou regras) e criação com um clique."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import bots as bots_api
from app.api import robots as robots_api
from app.core.engine import manager
from app.core.exchange import SymbolRules
from app.main import app
from app.services import backtesting, ranking
from app.services.llm import AIConfig

from .conftest import FakeMarket, make_ohlcv

EMAIL, PASSWORD = "robos@test.dev", "senha-robos-1"


class CoinMarket(FakeMarket):
    """Mercado falso com o que a tela de escolha usa (lista de moedas, instrumento, ticker)."""

    def tickers(self):
        return {
            "BTCUSDT": {"price": 84000.0, "change_pct": 1.5, "quote_volume": 9e8},
            "SOLUSDT": {"price": 120.0, "change_pct": -2.0, "quote_volume": 3e8},
            "USDCUSDT": {"price": 1.0, "change_pct": 0.0, "quote_volume": 5e9},  # estável: fica de fora
            "NOVOUSDUSDT": {"price": 1.0003, "change_pct": 0.01, "quote_volume": 4e9},  # estável fora da lista: também
            "ETHBTC": {"price": 0.03, "change_pct": 0.1, "quote_volume": 1e3},
        }

    def inst(self, symbol):
        if symbol not in ("SOLUSDT", "BTCUSDT"):
            raise ValueError(f"Par não encontrado na OKX: {symbol}")
        return {"instId": symbol[:-4] + "-USDT", "baseCcy": symbol[:-4], "quoteCcy": "USDT"}

    def symbol_rules(self, symbol):
        return SymbolRules(symbol, symbol[:-4], "USDT", tick_size=0.01, step_size=0.001, min_qty=0.001, min_notional=1.0)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    market = CoinMarket()
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: make_ohlcv(min(bars, 2500), seed=len(symbol) + len(interval), interval=interval))
    monkeypatch.setattr(robots_api, "get_market", lambda *a, **k: market)
    monkeypatch.setattr(bots_api, "get_market", lambda *a, **k: market)
    monkeypatch.setattr(manager, "market_factory", lambda db, bot: market)
    monkeypatch.setattr(manager, "spawn", lambda bot_id: None)
    monkeypatch.setattr("app.services.stats.prices.get", lambda symbol, *a, **k: market.current)
    ranking.clear_cache()
    yield
    ranking.clear_cache()


def test_catalog_uses_validated_rules():
    robots = ranking.catalog("baixa")
    assert len(robots) == 14 and {r["interval"] for r in robots} == {"4h", "1d"}
    squeeze = ranking.find_robot("baixa", "squeeze:4h")
    assert squeeze["name"] == "Squeeze 4h" and squeeze["risk"]["stop_loss_atr_mult"] == 3.0
    assert squeeze["risk"]["sentiment_filter"] == "avoid_extreme_fear"
    fast = ranking.find_robot("alta", "ignition:5m")
    assert fast["params"]["htf_ema"] == 1152 and fast["risk"]["trailing_enabled"] is True
    assert ranking.find_robot("baixa", "ignition:5m") is None  # robô de outra volatilidade


def test_rank_orders_best_to_worst_and_projects_amount():
    result = ranking.rank("SOLUSDT", "baixa")
    robots = result["robots"]
    assert len(robots) == 14 and [r["position"] for r in robots] == list(range(1, 15))
    eligible = [r for r in robots if r["eligible"]]
    assert eligible == robots[: len(eligible)]  # quem tem poucas operações fica no fim
    assert [r["score"] for r in eligible] == sorted((r["score"] for r in eligible), reverse=True)
    assert result["best"] == robots[0]["key"]
    assert result["worst"] == (eligible[-1] if len(eligible) > 1 else min(robots[1:], key=lambda r: r["score"]))["key"]
    assert result["coin"]["daily_volatility_pct"] > 0
    view = ranking.with_amount(result, 200)
    first = view["robots"][0]
    assert first["final_usdt"] == pytest.approx(200 * (1 + first["return_pct"] / 100), abs=0.01)
    assert ranking.rank("SOLUSDT", "baixa") is result  # cache


def _row(key: str, score: float, eligible: bool) -> dict:
    return {"key": key, "score": score, "eligible": eligible}


def test_worst_ignores_robots_with_few_trades():
    row = _row
    rows = [row("a", 30, True), row("b", 10, True), row("c", -20, True), row("sorte", 15, False)]
    best, worst = ranking.best_and_worst(rows)
    assert best["key"] == "a" and worst["key"] == "c"  # não o último da lista, que operou 1 vez
    best, worst = ranking.best_and_worst([row("a", 30, True), row("x", 50, False), row("y", -5, False)])
    assert best["key"] == "a" and worst["key"] == "y"  # só um robô elegível: o pior sai dos demais
    best, worst = ranking.best_and_worst([row("x", 5, False)])
    assert best is worst


def test_advice_rules_and_ai():
    result = ranking.rank("SOLUSDT", "media")
    rules = ranking.advise(result, 100, None)
    assert rules["source"] == "rules" and rules["recommended_key"] == result["best"]

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        reply = {"recommended_key": result["robots"][1]["key"], "headline": "Use o segundo.", "why": "Mais consistente.",
                 "watch_out": "Comece no simulado.", "confidence": "media"}  # fmt: skip
        return SimpleNamespace(stop_reason="end_turn", model=kwargs["model"], content=[SimpleNamespace(type="text", text=json.dumps(reply))])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    ai = AIConfig("anthropic", "sk-test", "claude-opus-5", "claude-haiku-4-5")
    out = ranking.advise(result, 100, ai, client=client)
    assert out["source"] == "ai" and out["recommended_key"] == result["robots"][1]["key"]
    sent = calls[0]["messages"][0]["content"]
    assert '"ranking"' in sent and "<noticias_recentes>" in sent and calls[0]["output_config"]["format"]["type"] == "json_schema"

    def invented(**kwargs):
        reply = {"recommended_key": "nao:existe", "headline": "x", "why": "y", "watch_out": "z", "confidence": "alta"}
        return SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(type="text", text=json.dumps(reply))])

    out = ranking.advise(result, 100, ai, client=SimpleNamespace(messages=SimpleNamespace(create=invented)))
    assert out["recommended_key"] == result["best"]  # a IA não inventa robô


@pytest.fixture(scope="module")
def api(fresh_db):
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
        yield c


def test_coins_and_coin_profile(api):
    coins = api.get("/api/robots/coins").json()
    assert [c["symbol"] for c in coins] == ["BTCUSDT", "SOLUSDT"]  # por volume, sem estáveis nem pares contra BTC
    assert coins[0]["name"] == "Bitcoin"
    info = api.get("/api/robots/coin/sol-usdt").json()
    assert info["base"] == "SOL" and info["name"] == "Solana" and info["daily_volatility_pct"] > 0 and info["wallet"] is None
    assert api.get("/api/robots/coin/NAOEXISTEUSDT").status_code == 404
    assert [lv["key"] for lv in api.get("/api/robots/levels").json()] == ["baixa", "media", "alta"]


def test_rank_advice_and_create_with_one_click(api):
    body = {"symbol": "SOLUSDT", "level": "baixa", "amount": 150}
    ranked = api.post("/api/robots/rank", json=body).json()
    assert len(ranked["robots"]) == 14 and ranked["amount"] == 150
    advice = api.post("/api/robots/advice", json=body).json()
    assert advice["recommended_key"] == ranked["best"]

    r = api.post("/api/robots/create", json={**body, "robot_key": ranked["best"], "mode": "paper", "start": True})
    assert r.status_code == 200, r.text
    bot = r.json()
    strategy, interval = ranked["best"].split(":")
    assert bot["strategy"] == strategy and bot["interval"] == interval and bot["status"] == "running"
    assert bot["risk"]["sizing_mode"] == "fixed_quote" and bot["risk"]["order_size_quote"] == 150
    assert bot["paper_initial_balance"] == 150 and bot["name"].startswith("SOL · ")

    assert api.post("/api/robots/create", json={**body, "robot_key": "inventado:4h"}).status_code == 400
    # dinheiro real exige a chave da OKX
    r = api.post("/api/robots/create", json={**body, "robot_key": ranked["best"], "mode": "live"})
    assert r.status_code == 400 and "OKX" in r.json()["detail"]
    assert api.post("/api/robots/rank", json={**body, "amount": 1}).status_code == 422  # valor mínimo
