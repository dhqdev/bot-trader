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
    monkeypatch.setattr(bots_api, "get_market", lambda demo=False, region="global": market)
    monkeypatch.setattr(manager, "market_factory", lambda db, bot: market)
    monkeypatch.setattr(manager, "spawn", lambda bot_id: None)  # sem threads nos testes
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: make_ohlcv(min(bars, 3000)))
    monkeypatch.setattr("app.services.stats.prices.get", lambda symbol, *args, **kwargs: market.current)
    monkeypatch.setattr("app.core.okx.inspect_okx_key", fake_inspect)


SAFE_PERMISSIONS = {
    "reading": True, "spot_trading": True, "withdrawals": False, "internal_transfer": False,
    "universal_transfer": False, "margin": False, "futures": False, "ip_restricted": True, "account_mode": "Spot (simples)",
}  # fmt: skip


def fake_inspect(api_key, api_secret, passphrase, demo=False, region="global"):
    return {"can_trade": True, "account_type": "Spot (simples)", "permissions": dict(SAFE_PERMISSIONS)}


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
    # trocar chaves exige a senha
    body = {"api_key": key, "api_secret": secret, "passphrase": "Frase#Secreta1"}
    assert client.put("/api/settings/okx", json=body).status_code == 403
    r = client.put("/api/settings/okx", json={**body, "password": "senha-forte-1"})
    assert r.status_code == 200, r.text
    body = client.get("/api/settings/credentials").json()
    assert body["okx"]["configured"] is True
    assert body["okx"]["api_key"] == "ABCD••••3456"
    assert "binance" not in body and "Frase#Secreta1" not in str(body)
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
    assert data["default"] == "squeeze" and data["default_interval"] == "4h" and len(data["strategies"]) == 7
    tiers = client.get("/api/profiles").json()["tiers"]
    assert [t["key"] for t in tiers] == ["rapido", "medio", "lento"]
    assert tiers[0]["warning"] and all(t["profiles"] for t in tiers)
    r = client.post("/api/backtest", json={"symbol": "SOLUSDT", "interval": "1h", "strategy": "squeeze", "days": 60})
    assert r.status_code == 200, r.text
    res = r.json()
    assert "metrics" in res and res["candles"] and res["equity_curve"]


def test_system_engine_toggle(client):
    assert client.post("/api/system/engine", json={"enabled": False}).json()["engine_enabled"] is False
    assert client.post("/api/system/engine", json={"enabled": True}).json()["engine_enabled"] is True


def test_ai_status_without_key(client):
    assert client.get("/api/ai/status").json()["configured"] is False


def test_pwa_files_are_served(client, tmp_path, monkeypatch):
    """Com o frontend compilado presente, manifesto e service worker saem com tipo e cache corretos."""
    import importlib

    from app import main as main_mod

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (dist / "sw.js").write_text("self.addEventListener('fetch', () => {});", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name": "Bot Trader"}', encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("BT_FRONTEND_DIST", str(dist))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fresh = importlib.reload(main_mod)
        with TestClient(fresh.app) as c:
            r = c.get("/manifest.webmanifest")
            assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
            r = c.get("/sw.js")
            assert r.status_code == 200 and "javascript" in r.headers["content-type"] and r.headers["cache-control"] == "no-cache"
            assert "immutable" in c.get("/assets/app-abc123.js").headers["cache-control"]
            r = c.get("/bots/123")  # rota da SPA devolve o index.html
            assert r.status_code == 200 and "text/html" in r.headers["content-type"] and r.headers["cache-control"] == "no-cache"
            assert c.get("/api/nao-existe").status_code == 404
    finally:
        monkeypatch.delenv("BT_FRONTEND_DIST")
        get_settings.cache_clear()
        importlib.reload(main_mod)
