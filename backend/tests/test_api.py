import pytest
from fastapi.testclient import TestClient

from app.api import bots as bots_api
from app.core.engine import manager
from app.main import app
from app.services import backtesting

from .conftest import FakeMarket, make_ohlcv


@pytest.fixture(scope="module")
def client(fresh_db):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    market = FakeMarket()
    monkeypatch.setattr(bots_api, "get_market", lambda testnet=False: market)
    monkeypatch.setattr(manager, "market_factory", lambda db, bot: market)
    monkeypatch.setattr(manager, "spawn", lambda bot_id: None)  # sem threads nos testes
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: make_ohlcv(min(bars, 3000)))
    monkeypatch.setattr("app.services.stats.prices.get", lambda symbol, testnet=False: market.current)


def test_auth_flow(client):
    s = client.get("/api/auth/status").json()
    assert s["user"] is None
    assert client.get("/api/bots").status_code == 401

    r = client.post("/api/auth/register", json={"email": "Eu@Teste.dev", "password": "senha-forte-1", "name": "Eu"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "eu@teste.dev"
    assert client.get("/api/auth/me").status_code == 200

    # cadastro fecha depois do primeiro usuário
    other = TestClient(app)
    assert other.post("/api/auth/register", json={"email": "x@y.z", "password": "12345678"}).status_code == 403

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "eu@teste.dev", "password": "errada"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "eu@teste.dev", "password": "senha-forte-1"}).status_code == 200


def test_credentials_are_masked(client):
    key, secret = "ABCDEFGHIJKLMNOPQRSTUV123456", "SECRETSECRETSECRETSECRET999"
    assert client.put("/api/settings/binance", json={"api_key": key, "api_secret": secret}).status_code == 200
    body = client.get("/api/settings/credentials").json()
    assert body["binance"]["configured"] is True
    assert body["binance"]["api_key"] == "ABCD••••3456"
    assert secret not in str(body) and key not in str(body)


def test_bot_lifecycle(client):
    r = client.post(
        "/api/bots",
        json={"name": "SOL confluência", "symbol": "sol/usdt", "interval": "1h", "strategy": "confluence", "mode": "paper"},
    )
    assert r.status_code == 200, r.text
    bot = r.json()
    assert bot["symbol"] == "SOLUSDT" and bot["status"] == "stopped"
    assert bot["strategy_params"]["ema_fast"] == 9  # padrões aplicados

    bot_id = bot["id"]
    r = client.put(f"/api/bots/{bot_id}", json={"strategy_params": {"ema_fast": 12}, "risk": {"order_size_quote": 50}})
    assert r.status_code == 200
    assert r.json()["strategy_params"]["ema_fast"] == 12
    assert r.json()["risk"]["order_size_quote"] == 50

    assert client.post(f"/api/bots/{bot_id}/start").json()["status"] == "running"
    assert client.delete(f"/api/bots/{bot_id}").status_code == 400  # precisa parar antes
    assert client.post(f"/api/bots/{bot_id}/stop").json()["status"] == "stopped"

    chart = client.get(f"/api/bots/{bot_id}/chart?limit=100").json()
    assert len(chart["candles"]) == 100 and "preview" in chart and chart["overlays"]

    assert client.get(f"/api/bots/{bot_id}/events").json()
    assert client.get("/api/dashboard").json()["summary"]["total_bots"] >= 1
    assert client.delete(f"/api/bots/{bot_id}").status_code == 200


def test_invalid_bot_input(client):
    assert client.post("/api/bots", json={"name": "x", "symbol": "SOLUSDT", "interval": "7m"}).status_code == 422
    assert client.post("/api/bots", json={"name": "x", "symbol": "SOLUSDT", "strategy": "nope"}).status_code == 422
    r = client.post("/api/bots", json={"name": "x", "symbol": "SOLUSDT", "risk": {"stop_loss_pct": -1}})
    assert r.status_code == 422


def test_strategies_and_backtest(client):
    data = client.get("/api/strategies").json()
    assert data["default"] == "confluence" and len(data["strategies"]) == 7
    r = client.post("/api/backtest", json={"symbol": "SOLUSDT", "interval": "1h", "strategy": "supertrend", "days": 60})
    assert r.status_code == 200, r.text
    res = r.json()
    assert "metrics" in res and res["candles"] and res["equity_curve"]


def test_system_engine_toggle(client):
    assert client.post("/api/system/engine", json={"enabled": False}).json()["engine_enabled"] is False
    assert client.post("/api/system/engine", json={"enabled": True}).json()["engine_enabled"] is True


def test_ai_requires_key(client):
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert r.status_code == 400
