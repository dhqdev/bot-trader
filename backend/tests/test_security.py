"""Segurança do site: cabeçalhos, CSRF, bloqueio de tentativas, 2FA, sessões e chaves."""

import time

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import session_scope
from app.main import app
from app.models import User, UserSecurity
from app.security import COOKIE_NAME, create_2fa_ticket

EMAIL, PASSWORD = "dono@teste.dev", "senha-muito-forte-1"
SAFE = {"reading": True, "spot_trading": True, "withdrawals": False, "internal_transfer": False,
        "universal_transfer": False, "margin": False, "futures": False, "ip_restricted": False}  # fmt: skip


@pytest.fixture(scope="module")
def client(fresh_db):
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "name": "Dono"})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
def permissions(monkeypatch):
    perms = dict(SAFE)
    monkeypatch.setattr(
        "app.core.okx.inspect_okx_key",
        lambda key, secret, passphrase, demo=False, region="global": {"can_trade": True, "account_type": "Spot (simples)", "permissions": perms},
    )
    return perms


def login(email=EMAIL, password=PASSWORD) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def _user_id() -> int:
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.email == EMAIL))


def test_security_headers(client):
    r = client.get("/api/health")
    h = r.headers
    assert h["cache-control"] == "no-store"
    assert "script-src 'self'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in h["permissions-policy"]


def test_session_cookie_is_strict_and_http_only():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_csrf_blocks_other_origins(client):
    body = {"email": EMAIL, "password": "x"}
    assert client.post("/api/auth/login", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    # subdomínio do mesmo domínio também é bloqueado (o SameSite não cobre)
    assert client.post("/api/auth/login", json=body, headers={"Origin": "https://n8n.testserver"}).status_code == 403
    assert client.post("/api/auth/login", json=body, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    # mesma origem passa (e cai na senha errada)
    assert client.post("/api/auth/login", json=body, headers={"Origin": "http://testserver"}).status_code == 401
    # GET não muda nada: não é bloqueado
    assert client.get("/api/auth/status", headers={"Origin": "https://evil.example"}).status_code == 200


def test_body_size_limit(client):
    r = client.post("/api/auth/login", content=b"{" + b" " * 1_100_000 + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_account_lockout_after_failures():
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": EMAIL, "password": "errada"}).status_code == 401
    # bloqueada: nem a senha certa entra por um tempo
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 429
    # e-mail inexistente responde igual a senha errada (não revela quem tem conta)
    r = c.post("/api/auth/login", json={"email": "ninguem@x.dev", "password": "abcdefgh"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha incorretos."


def test_okx_keys_need_password_and_no_withdrawals(client, permissions):
    keys = {"api_key": "K" * 30, "api_secret": "S" * 30, "passphrase": "Frase#1"}
    assert client.put("/api/settings/okx", json=keys).status_code == 403
    assert client.put("/api/settings/okx", json={**keys, "password": "errada"}).status_code == 403

    permissions["withdrawals"] = True
    r = client.put("/api/settings/okx", json={**keys, "password": PASSWORD})
    assert r.status_code == 400 and "SAQUE" in r.json()["detail"]
    assert client.get("/api/settings/credentials").json()["okx"]["configured"] is False

    permissions["withdrawals"] = False
    r = client.put("/api/settings/okx", json={**keys, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert any("IP" in w for w in r.json()["warnings"])  # chave sem restrição de IP gera aviso
    creds = client.get("/api/settings/credentials").json()["okx"]
    assert creds["configured"] and creds["permissions"]["withdrawals"] is False and creds["warnings"]


def test_logout_all_devices(client):
    other = login()
    assert other.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout-all").status_code == 200
    assert other.get("/api/auth/me").status_code == 401  # o outro aparelho caiu
    assert other.get("/api/auth/status").json()["user"] is None
    assert client.get("/api/auth/me").status_code == 200  # este continua


def test_password_change_drops_other_sessions(client):
    other = login()
    r = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD + "x"})
    assert r.status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200
    r = client.post("/api/auth/password", json={"current_password": PASSWORD + "x", "new_password": PASSWORD})
    assert r.status_code == 200


def test_two_factor_flow(client):
    assert client.post("/api/security/2fa/setup", json={"password": "errada"}).status_code == 403
    setup = client.post("/api/security/2fa/setup", json={"password": PASSWORD}).json()
    assert setup["qr"].startswith("data:image/svg+xml") and setup["uri"].startswith("otpauth://totp/")
    totp = pyotp.TOTP(setup["secret"])

    assert client.post("/api/security/2fa/enable", json={"code": "000000"}).status_code == 400
    r = client.post("/api/security/2fa/enable", json={"code": totp.now()})
    assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    assert client.get("/api/security/status").json()["two_factor"] == {"enabled": True, "recovery_codes_left": 10}

    # login agora tem duas etapas: a senha sozinha não cria sessão
    c = TestClient(app)
    first = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()
    assert first["two_factor_required"] is True and COOKIE_NAME not in c.cookies
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login/2fa", json={"ticket": first["ticket"], "code": "123456"}).status_code == 401
    # o código do próximo intervalo de 30 s ainda vale (relógios fora de sincronia)
    next_code = totp.at(time.time() + 30)
    assert c.post("/api/auth/login/2fa", json={"ticket": first["ticket"], "code": next_code}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200

    # o mesmo código não vale duas vezes
    c2 = TestClient(app)
    ticket = c2.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["ticket"]
    assert c2.post("/api/auth/login/2fa", json={"ticket": ticket, "code": next_code}).status_code == 401
    # código de recuperação funciona uma única vez
    assert c2.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[0].upper()}).status_code == 200
    c3 = TestClient(app)
    ticket = c3.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["ticket"]
    assert c3.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[0]}).status_code == 401

    # o ticket da etapa 2 não serve como sessão
    c4 = TestClient(app)
    c4.cookies.set(COOKIE_NAME, create_2fa_ticket(_user_id(), 0))
    assert c4.get("/api/auth/me").status_code == 401

    # com 2FA, ações sensíveis pedem senha + código
    assert client.post("/api/security/2fa/disable", json={"password": PASSWORD}).status_code == 403
    assert client.post("/api/security/2fa/disable", json={"password": PASSWORD, "code": codes[1]}).status_code == 200
    assert client.get("/api/security/status").json()["two_factor"]["enabled"] is False
    with session_scope() as db:
        sec = db.get(UserSecurity, _user_id())
        assert sec.totp_secret_enc is None and sec.recovery_codes == []


def test_security_events_are_recorded(client):
    kinds = {e["kind"] for e in client.get("/api/security/events?limit=200").json()}
    assert {"register", "login_ok", "login_fail", "logout_all", "password_changed", "2fa_enabled", "2fa_disabled",
            "recovery_used", "okx_keys_saved", "okx_keys_rejected"} <= kinds  # fmt: skip
    event = client.get("/api/security/events").json()[0]
    assert event["label"] and "created_at" in event


def test_rate_limiter_does_not_grow_without_bound():
    from app.security import LoginRateLimiter

    limiter = LoginRateLimiter(3, 60)
    for i in range(50):
        assert limiter.check(f"ninguem{i}@x.dev")  # consultar não guarda nada
    assert len(limiter._attempts) == 0
    limiter.MAX_KEYS = 20
    for i in range(100):
        limiter.hit(f"k{i}")
    assert len(limiter._attempts) <= 20
    for _ in range(3):
        limiter.hit("alvo")
    assert limiter.check("alvo") is False and limiter.check("outro") is True
