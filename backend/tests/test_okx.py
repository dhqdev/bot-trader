"""OKX: assinatura, candles, regras, ordens (com taxas), permissões, API e migração do banco."""

import base64
import hashlib
import hmac
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api import bots as bots_api
from app.core import engine as engine_mod
from app.core import okx
from app.core.exchange import now_ms
from app.db import _add_missing_columns
from app.main import app

SECRET = "segredo-de-teste"
STEP_4H = 4 * 3600 * 1000


def ok(data, code="0", msg=""):
    return httpx.Response(200, json={"code": code, "msg": msg, "data": data})


class FakeOkx:
    """Servidor OKX falso: responde como a API v5 e registra as requisições."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.order_states = ["live", "filled"]
        self.fail_place_transport = False
        self.placed: list[dict] = []
        self.expired_once = False
        now = now_ms()
        last_closed = (now // STEP_4H) * STEP_4H - STEP_4H
        # 1500 candles de 4h (o mais recente ainda aberto), do mais novo para o mais velho, como a OKX devolve
        self.candles = [
            [str(last_closed + STEP_4H - i * STEP_4H), "100", "110", "90", str(100 + i % 7), "5", "500", "500", "0" if i == 0 else "1"]
            for i in range(1500)
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, q = request.url.path, dict(request.url.params)
        if path == "/api/v5/public/time":
            return ok([{"ts": str(now_ms())}])
        if path == "/api/v5/public/instruments":
            return ok([
                {"instId": "SOL-USDT", "baseCcy": "SOL", "quoteCcy": "USDT", "minSz": "0.01", "lotSz": "0.000001", "tickSz": "0.01", "state": "live"},
                {"instId": "ETH-BTC", "baseCcy": "ETH", "quoteCcy": "BTC", "minSz": "0.001", "lotSz": "0.0001", "tickSz": "0.00001", "state": "live"},
                {"instId": "OLD-USDT", "baseCcy": "OLD", "quoteCcy": "USDT", "minSz": "1", "lotSz": "1", "tickSz": "0.1", "state": "suspend"},
            ])  # fmt: skip
        if path == "/api/v5/market/ticker":
            return ok([{"instId": q["instId"], "last": "100", "open24h": "80", "high24h": "101", "low24h": "79", "volCcy24h": "12345"}])
        if path == "/api/v5/market/tickers":
            return ok([{"instId": "SOL-USDT", "last": "100"}, {"instId": "ETH-BTC", "last": "0.05"}])
        if path in ("/api/v5/market/candles", "/api/v5/market/history-candles"):
            after = int(q["after"]) if "after" in q else None
            rows = [c for c in self.candles if after is None or int(c[0]) < after]
            limit = int(q["limit"])
            if path.endswith("/candles"):  # o endpoint recente só alcança os ~1440 mais novos
                rows = [c for c in rows if self.candles.index(c) < 1440]
            return ok(rows[:limit])
        if path == "/api/v5/account/config":
            return ok([{"acctLv": "1", "perm": "read_only,trade", "ip": "203.0.113.7"}])
        if path == "/api/v5/account/trade-fee":  # conta do Brasil no nível Lv1
            return ok([{"instType": "SPOT", "level": "Lv1", "maker": "-0.001", "taker": "-0.004"}])
        if path == "/api/v5/account/balance":
            if not self.expired_once:
                self.expired_once = True
                return httpx.Response(401, json={"code": "50102", "msg": "Timestamp request expired", "data": []})
            return ok([{"details": [{"ccy": "USDT", "availBal": "250.5", "frozenBal": "0", "cashBal": "250.5"},
                                    {"ccy": "SOL", "availBal": "", "frozenBal": "0.5", "cashBal": "2.5"}]}])  # fmt: skip
        if path == "/api/v5/trade/order" and request.method == "POST":
            body = json.loads(request.content)
            self.placed.append(body)
            if self.fail_place_transport:
                raise httpx.ReadTimeout("sem resposta", request=request)
            if body["sz"] == "0.00":
                return ok([{"ordId": "", "sCode": "51008", "sMsg": "Order failed. Insufficient USDT balance in account."}], code="1", msg="")
            return ok([{"ordId": "777", "clOrdId": body.get("clOrdId", ""), "sCode": "0", "sMsg": ""}])
        if path == "/api/v5/trade/order" and request.method == "GET":
            placed = self.placed[-1] if self.placed else {"side": "buy", "sz": "1"}
            state = self.order_states.pop(0) if len(self.order_states) > 1 else self.order_states[0]
            if placed["side"] == "buy":  # comprou 0,5 SOL a 100; taxa de 0,1% cobrada em SOL
                return ok([{"ordId": "777", "side": "buy", "state": state, "accFillSz": "0.5", "avgPx": "100", "fee": "-0.0005", "feeCcy": "SOL"}])
            return ok([{"ordId": "777", "side": "sell", "state": state, "accFillSz": placed["sz"], "avgPx": "110", "fee": "-0.055", "feeCcy": "USDT"}])
        return httpx.Response(404, json={"code": "404", "msg": f"rota falsa não existe: {path}", "data": []})


@pytest.fixture
def fake():
    return FakeOkx()


def client_for(fake: FakeOkx, **kw) -> okx.OkxClient:
    return okx.OkxClient("minha-chave", SECRET, "minha-passphrase", transport=httpx.MockTransport(fake.handler), **kw)


def market_for(fake: FakeOkx) -> okx.OkxMarketData:
    return okx.OkxMarketData(client=okx.OkxClient(transport=httpx.MockTransport(fake.handler)))


def trader_for(fake: FakeOkx) -> okx.OkxTrader:
    trader = okx.OkxTrader("minha-chave", SECRET, "minha-passphrase", client=client_for(fake), market=market_for(fake))
    trader.poll_delay = 0
    return trader


def test_signature_headers_and_demo(fake):
    client = client_for(fake, demo=True)
    client.private("GET", "/api/v5/trade/order", {"instId": "SOL-USDT", "ordId": "1"})
    client.private("POST", "/api/v5/trade/order", body={"instId": "SOL-USDT", "sz": "10"})
    assert fake.requests[0].url.path == "/api/v5/public/time"  # sincroniza o relógio antes
    for req in fake.requests[1:]:
        h = req.headers
        assert h["OK-ACCESS-KEY"] == "minha-chave" and h["OK-ACCESS-PASSPHRASE"] == "minha-passphrase"
        assert h["x-simulated-trading"] == "1"
        ts = h["OK-ACCESS-TIMESTAMP"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)
        # assinatura = Base64(HMAC-SHA256(segredo, timestamp + MÉTODO + caminho com a query + corpo))
        prehash = ts + req.method + req.url.raw_path.decode() + req.content.decode()
        expected = base64.b64encode(hmac.new(SECRET.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
        assert h["OK-ACCESS-SIGN"] == expected
    assert fake.requests[1].url.raw_path.decode() == "/api/v5/trade/order?instId=SOL-USDT&ordId=1"
    assert fake.requests[2].content == b'{"instId":"SOL-USDT","sz":"10"}'
    # conta real: sem o cabeçalho de demonstração
    real = client_for(FakeOkx())
    assert "x-simulated-trading" not in real._base_headers()


def test_errors_and_clock_resync(fake):
    client = client_for(fake)
    balance = client.private("GET", "/api/v5/account/balance")  # 1ª resposta: relógio fora (50102) -> ressincroniza
    assert balance[0]["details"][0]["ccy"] == "USDT"
    assert sum(r.url.path == "/api/v5/public/time" for r in fake.requests) == 2
    with pytest.raises(okx.OkxError) as err:
        client.private("POST", "/api/v5/trade/order", body={"sz": "0.00"})
    assert err.value.code == "51008" and "Insufficient" in err.value.message  # motivo detalhado da ordem
    with pytest.raises(okx.OkxError):
        okx.OkxClient().private("GET", "/api/v5/account/balance")  # sem chaves


def test_klines_paginate_and_skip_open_candle(fake):
    m = market_for(fake)
    df = m.klines("SOLUSDT", "4h", limit=1450)
    assert len(df) == 1450 and df["time"].is_monotonic_increasing and df["time"].diff().dropna().eq(STEP_4H).all()
    assert int(df["time"].iloc[-1]) == int(fake.candles[1][0])  # o candle ainda aberto ficou de fora
    assert int(df["close_time"].iloc[-1]) == int(fake.candles[1][0]) + STEP_4H - 1
    used = {r.url.path for r in fake.requests}
    assert "/api/v5/market/history-candles" in used  # passou dos 1440 recentes e foi ao histórico
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume", "close_time"]
    live = m.klines("SOLUSDT", "4h", limit=5, closed_only=False)
    assert int(live["time"].iloc[-1]) == int(fake.candles[0][0])
    with pytest.raises(ValueError):
        m.klines("SOLUSDT", "8h", limit=5)  # a OKX não tem candle de 8h
    with pytest.raises(ValueError):
        m.klines("NAOEXISTEUSDT", "4h", limit=5)


def test_symbols_rules_and_prices(fake):
    m = market_for(fake)
    assert m.inst_id("SOLUSDT") == "SOL-USDT" and m.inst_id("sol-usdt") == "SOL-USDT"
    assert [s["symbol"] for s in m.symbols("USDT")] == ["SOLUSDT"]  # suspenso não aparece
    rules = m.symbol_rules("SOLUSDT")
    assert (rules.base, rules.quote, rules.step_size, rules.min_qty, rules.quote_precision) == ("SOL", "USDT", 0.000001, 0.01, 2)
    assert rules.min_notional == pytest.approx(1.05)  # 0,01 SOL x 100, com 5% de folga (nunca menos de 1 USDT)
    assert m.symbol_rules("ETHBTC").quote_precision == 8
    assert m.price("SOLUSDT") == 100.0 and m.prices() == {"SOLUSDT": 100.0, "ETHBTC": 0.05}
    assert m.ticker_24h("SOLUSDT")["change_pct"] == pytest.approx(25.0)


def test_market_buy_and_sell_with_fees(fake):
    trader = trader_for(fake)
    m = trader.market
    rules = m.symbol_rules("SOLUSDT")
    buy = trader.market_buy_quote("SOLUSDT", 50.129, rules)
    sent = fake.placed[-1]
    assert sent["side"] == "buy" and sent["ordType"] == "market" and sent["tdMode"] == "cash"
    assert sent["tgtCcy"] == "quote_ccy" and sent["sz"] == "50.12"  # compra em USDT, 2 casas
    assert len(sent["clOrdId"]) <= 32 and sent["clOrdId"].isalnum()
    # esperou a ordem terminar (live -> filled) e descontou a taxa cobrada em SOL
    assert buy.status == "FILLED" and buy.qty == 0.5 and buy.net_qty == pytest.approx(0.4995)
    assert buy.fee_quote == pytest.approx(0.05) and buy.net_quote == pytest.approx(50.0)

    fake.order_states = ["filled"]
    sell = trader.market_sell_qty("SOLUSDT", 0.4995009, rules)
    sent = fake.placed[-1]
    assert sent["side"] == "sell" and sent["tgtCcy"] == "base_ccy" and sent["sz"] == "0.499500"
    assert sell.fee_quote == pytest.approx(0.055) and sell.net_quote == pytest.approx(0.4995 * 110 - 0.055)


def test_order_found_by_client_id_after_timeout(fake):
    trader = trader_for(fake)
    rules = trader.market.symbol_rules("SOLUSDT")
    fake.fail_place_transport = True
    fake.order_states = ["filled"]
    fill = trader.market_buy_quote("SOLUSDT", 50, rules)  # a OKX executou, mas a resposta não chegou
    assert fill.qty == 0.5
    lookup = [r for r in fake.requests if r.method == "GET" and r.url.path == "/api/v5/trade/order"][0]
    assert lookup.url.params["clOrdId"] == fake.placed[-1]["clOrdId"]


def test_account_permissions_and_balances(fake):
    trader = trader_for(fake)
    perms = trader.api_permissions()
    assert perms["withdrawals"] is False and perms["spot_trading"] is True and perms["ip_restricted"] is True
    assert perms["account_mode"] == "Spot (simples)"
    bal = trader.balances()  # 1ª consulta volta com relógio fora e é repetida
    assert bal["USDT"] == (250.5, 0.0) and bal["SOL"] == (2.0, 0.5)  # sem availBal: saldo - congelado
    assert okx._perm_list("read_only, Trade,WITHDRAW") == ["read_only", "trade", "withdraw"]


def test_taker_fee_is_read_from_the_account(fake):
    trader = trader_for(fake)
    assert trader.taker_fee_pct("SOLUSDT") == 0.4  # a OKX devolve -0.004: taxa cobrada de 0,4%
    req = fake.requests[-1]
    assert req.url.path == "/api/v5/account/trade-fee" and dict(req.url.params) == {"instType": "SPOT", "instId": "SOL-USDT"}


# ---------------------------------------------------------------------------
# API e motor


def test_okx_keys_api(monkeypatch, fresh_db):
    perms = {"reading": True, "spot_trading": True, "withdrawals": False, "internal_transfer": False, "universal_transfer": False,
             "margin": False, "futures": False, "ip_restricted": False, "account_mode": "Spot (simples)"}  # fmt: skip
    seen = {}

    def inspect(key, secret, passphrase, demo=False, region="global"):
        seen.update(key=key, passphrase=passphrase, region=region, demo=demo)
        return {"can_trade": True, "account_type": "Spot (simples)", "permissions": dict(perms)}

    monkeypatch.setattr(okx, "inspect_okx_key", inspect)
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"email": "okx@test.dev", "password": "senha-okx-123"}).status_code == 200
        body = {"api_key": "okx-api-key-123456", "api_secret": "okx-secret-abcdef", "passphrase": "Minha#Frase1", "region": "global"}
        assert c.put("/api/settings/okx", json=body).status_code == 403  # sem a senha
        perms["withdrawals"] = True
        r = c.put("/api/settings/okx", json={**body, "password": "senha-okx-123"})
        assert r.status_code == 400 and "SAQUE" in r.json()["detail"]
        perms["withdrawals"] = False
        r = c.put("/api/settings/okx", json={**body, "password": "senha-okx-123", "demo": True})
        assert r.status_code == 200, r.text
        assert seen == {"key": "okx-api-key-123456", "passphrase": "Minha#Frase1", "region": "global", "demo": True}
        assert any("IP" in w for w in r.json()["warnings"])
        creds = c.get("/api/settings/credentials").json()["okx"]
        assert creds["configured"] and creds["demo"] is True and creds["region"] == "global" and creds["api_key"] == "okx-••••3456"
        raw = str(c.get("/api/settings/credentials").json())
        assert "okx-secret-abcdef" not in raw and "Minha#Frase1" not in raw
        assert c.delete("/api/settings/okx").json()["ok"] is True
        assert c.get("/api/settings/credentials").json()["okx"]["configured"] is False


def test_bot_on_okx_uses_okx_market(monkeypatch, fresh_db, fake):
    from .conftest import FakeMarket

    fake_market = FakeMarket()
    calls = []

    def okx_market(demo=False, region="global"):
        calls.append((demo, region))
        return fake_market

    monkeypatch.setattr(bots_api, "get_market", okx_market)
    monkeypatch.setattr(engine_mod, "get_market", okx_market)
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"email": "okx@test.dev", "password": "senha-okx-123"})
        r = c.post("/api/bots", json={"name": "SOL OKX", "symbol": "SOL-USDT", "interval": "4h", "strategy": "squeeze", "mode": "paper"})
        assert r.status_code == 200, r.text
        bot = r.json()
        assert bot["symbol"] == "SOLUSDT" and calls == [(False, "global")]
        # modo real exige as chaves da OKX
        r = c.put(f"/api/bots/{bot['id']}", json={"mode": "live"})
        assert r.status_code == 400 and "OKX" in r.json()["detail"]
    from app.db import session_scope
    from app.models import Bot

    with session_scope() as db:
        b = db.get(Bot, bot["id"])
        assert b.exchange == "okx"
        engine_mod.bot_market(db, b)
    assert len(calls) == 2


def test_old_databases_get_the_exchange_column(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'velho.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE bots (id INTEGER PRIMARY KEY, name VARCHAR(120))"))
        conn.execute(text("INSERT INTO bots (id, name) VALUES (1, 'bot antigo')"))
    _add_missing_columns(eng)
    _add_missing_columns(eng)  # rodar de novo não quebra
    with eng.connect() as conn:
        assert conn.execute(text("SELECT exchange FROM bots WHERE id = 1")).scalar() == "binance"


def test_server_ip_for_key_binding(monkeypatch):
    from app.api import settings as settings_api

    settings_api._ip_cache.update(at=0.0, ip=None)
    monkeypatch.setattr(settings_api, "fetch_public_ip", lambda: "203.0.113.7")
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"email": "okx@test.dev", "password": "senha-okx-123"})
        assert c.get("/api/settings/server-ip").json() == {"ip": "203.0.113.7"}

        def broken():
            raise httpx.ConnectError("sem internet")

        settings_api._ip_cache.update(at=0.0, ip=None)
        monkeypatch.setattr(settings_api, "fetch_public_ip", broken)
        assert c.get("/api/settings/server-ip").json() == {"ip": None}



def test_legacy_binance_bots_move_to_okx(fresh_db):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Bot, BotEvent, Credential, Position, SecurityEvent, User
    from app.security import encrypt, hash_password

    with session_scope() as db:
        user = User(email="legado@test.dev", name="L", password_hash=hash_password("x" * 8))
        db.add(user)
        db.flush()
        common = dict(user_id=user.id, symbol="SOLUSDT", base_asset="SOL", quote_asset="USDT", interval="4h", strategy="squeeze",
                      strategy_params={}, risk={}, exchange="binance", status="running")  # fmt: skip
        paper, live = Bot(name="simulado", mode="paper", **common), Bot(name="real", mode="live", **common)
        db.add_all([paper, live])
        db.flush()
        db.add(Position(bot_id=live.id, symbol="SOLUSDT", mode="live", entry_price=100, initial_qty=2, qty=2, cost_quote=200, highest_price=100))
        db.add(Credential(user_id=user.id, provider="binance", key_enc=encrypt("k"), secret_enc=encrypt("s")))
        ids = (paper.id, live.id, user.id)
    with session_scope() as db:
        assert engine_mod.migrate_to_okx(db) == 2
    with session_scope() as db:
        paper, live = db.get(Bot, ids[0]), db.get(Bot, ids[1])
        assert paper.exchange == live.exchange == "okx"
        assert paper.status == "running"  # simulado continua
        assert live.status == "stopped" and "OKX" in live.status_reason  # real espera o usuário religar
        pos = db.scalar(select(Position).where(Position.bot_id == live.id))
        assert pos.status == "closed" and pos.exit_reason == "migrated" and pos.pnl_quote is None  # sem inventar prejuízo
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == live.id))]
        assert any("venda manualmente na Binance" in m for m in msgs)
        assert db.scalar(select(Credential).where(Credential.provider == "binance")) is None
        assert db.scalar(select(SecurityEvent).where(SecurityEvent.user_id == ids[2], SecurityEvent.kind == "binance_keys_removed"))
    with session_scope() as db:
        assert engine_mod.migrate_to_okx(db) == 0  # já migrado: nada a fazer


def test_rate_limit_waits_and_retries(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(429, json={"code": "50011", "msg": "Too Many Requests", "data": []})
        return ok([{"ts": "1"}])

    sleeps = []
    monkeypatch.setattr(okx.time, "sleep", lambda s: sleeps.append(s))
    client = okx.OkxClient(transport=httpx.MockTransport(handler))
    assert client.public("/api/v5/public/time") == [{"ts": "1"}]
    assert len(calls) == 2 and sleeps and sleeps[0] >= 0.5  # esperou antes de tentar de novo


def test_klines_before_a_given_time(fake):
    m = market_for(fake)
    newest = m.klines("SOLUSDT", "4h", limit=10)
    older = m.klines("SOLUSDT", "4h", limit=5, before=int(newest["time"].iloc[0]))
    assert len(older) == 5 and int(older["time"].iloc[-1]) == int(newest["time"].iloc[0]) - STEP_4H


class CountingMarket:
    """Mercado falso que conta quantos candles cada chamada pediu."""

    def __init__(self, fake: FakeOkx):
        self.inner = market_for(fake)
        self.requests: list[tuple[int, int | None]] = []

    def klines(self, symbol, interval, limit=500, closed_only=True, before=None):
        self.requests.append((limit, before))
        return self.inner.klines(symbol, interval, limit=limit, closed_only=closed_only, before=before)


def test_history_is_stored_and_only_missing_candles_are_fetched(monkeypatch, fake, fresh_db):
    from app.services import backtesting

    market = CountingMarket(fake)
    monkeypatch.setattr(backtesting, "get_market", lambda *a, **k: market)
    backtesting._cache.clear()
    first = backtesting.history("SOLUSDT", "4h", 300)
    assert len(first) == 300 and market.requests == [(300, None)]

    backtesting._cache.clear()  # memória vazia: vem do banco, sem pedir nada à OKX
    again = backtesting.history("SOLUSDT", "4h", 300)
    assert market.requests == [(300, None)] and again["time"].tolist() == first["time"].tolist()

    backtesting._cache.clear()  # pediu mais histórico: busca só os 200 mais antigos que faltam
    longer = backtesting.history("SOLUSDT", "4h", 500)
    assert market.requests[-1] == (200, int(first["time"].iloc[0]))
    assert len(longer) == 500 and longer["time"].is_monotonic_increasing and longer["time"].diff().dropna().eq(STEP_4H).all()
