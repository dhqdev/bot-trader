"""IA: escolha entre Claude e GPT e validação das chaves (a conversa com a IA foi retirada)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import llm

EMAIL, PASSWORD = "ai@test.dev", "12345678"


@pytest.fixture(scope="module")
def client(fresh_db):
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
        yield c


def test_status_without_keys(client):
    assert client.get("/api/ai/status").json() == {"configured": False, "provider": None, "provider_label": None, "model": None}
    # a conversa com a IA não existe mais
    assert client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "oi"}]}).status_code in (404, 405)


def test_latest_key_wins_and_user_can_switch(client, monkeypatch):
    monkeypatch.setattr(llm, "check_openai_key", lambda key, model: None)
    assert client.put("/api/settings/anthropic", json={"api_key": "sk-ant-test-123456", "password": PASSWORD}).status_code == 200
    assert client.get("/api/ai/status").json()["provider"] == "anthropic"

    r = client.put("/api/settings/openai", json={"api_key": "sk-proj-teste-123456", "model": "gpt-6-sol", "password": PASSWORD})
    assert r.status_code == 200, r.text
    status = client.get("/api/ai/status").json()
    assert status["provider"] == "openai" and status["model"] == "gpt-6-sol"

    creds = client.get("/api/settings/credentials").json()
    assert creds["ai"]["active"] == "openai" and creds["openai"]["api_key"] == "sk-p••••3456"
    assert "sk-proj-teste-123456" not in str(creds)
    assert client.put("/api/settings/ai-provider", json={"provider": "anthropic"}).json()["active"] == "anthropic"
    assert client.get("/api/ai/status").json()["provider"] == "anthropic"
    client.delete("/api/settings/openai")
    assert client.put("/api/settings/ai-provider", json={"provider": "openai"}).status_code == 400


def test_openai_key_needs_password_and_valid_key(client, monkeypatch):
    def reject(key, model):
        raise ValueError("Chave da OpenAI inválida. Confira se copiou a chave inteira (começa com sk-).")

    monkeypatch.setattr(llm, "check_openai_key", reject)
    client.delete("/api/settings/openai")
    body = {"api_key": "sk-proj-errada-999999", "model": "gpt-6-sol"}
    assert client.put("/api/settings/openai", json=body).status_code == 403  # sem a senha
    r = client.put("/api/settings/openai", json={**body, "password": PASSWORD})
    assert r.status_code == 400 and "inválida" in r.json()["detail"]
    assert client.get("/api/settings/credentials").json()["openai"]["configured"] is False
    # nome de modelo com caracteres estranhos é recusado antes de chegar na OpenAI
    assert client.put("/api/settings/openai", json={**body, "model": "gpt 6; rm -rf", "password": PASSWORD}).status_code == 422
