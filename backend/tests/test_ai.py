"""Loop do agente de IA com um cliente Anthropic falso (sem rede, sem custo)."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai as ai_mod


class FakeStream:
    def __init__(self, texts, final):
        self._texts = texts
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for t in self._texts:
                yield SimpleNamespace(type="text", text=t)

        return gen()

    async def get_final_message(self):
        return self._final


def block(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """1º turno: pede a ferramenta get_portfolio. 2º turno: responde em texto."""

    calls: list[dict] = []

    def __init__(self, api_key=None):
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        FakeClient.calls.append(kwargs)
        if len(FakeClient.calls) == 1:
            final = SimpleNamespace(
                stop_reason="tool_use",
                model="claude-opus-5",
                content=[
                    block(type="text", text="Vou consultar."),
                    block(type="tool_use", id="tu_1", name="get_portfolio", input={"mode": "all"}),
                ],
            )
            return FakeStream(["Vou consultar."], final)
        final = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5", content=[block(type="text", text="Tudo certo.")])
        return FakeStream(["Tudo ", "certo."], final)


@pytest.fixture
def fake_anthropic(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(ai_mod.anthropic, "AsyncAnthropic", FakeClient)
    return FakeClient


async def _collect(gen):
    return [e async for e in gen]


def test_agent_loop_runs_tools(fake_anthropic):
    events = asyncio.run(_collect(ai_mod.chat_stream(1, "sk-test", [{"role": "user", "content": "Como estão meus bots?"}], None, None)))
    types = [e["type"] for e in events]
    assert "tool" in types and "done" in types
    assert any(e["type"] == "tool_done" and e["ok"] for e in events)
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Vou consultar.Tudo certo."

    # 2ª chamada recebe o resultado da ferramenta
    second = fake_anthropic.calls[1]
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"
    assert "summary" in json.loads(tool_result["content"])
    # fallback server-side e ferramentas enviadas
    assert second["fallbacks"] == "default" and second["betas"] == ["server-side-fallback-2026-07-01"]
    assert {t["name"] for t in second["tools"]} >= {"run_backtest", "get_market_snapshot", "get_bot"}


def test_invalid_tool_input_is_reported(fake_anthropic, monkeypatch):
    original = FakeClient._stream

    def bad_stream(self, **kwargs):
        if not FakeClient.calls:
            FakeClient.calls.append(kwargs)
            final = SimpleNamespace(
                stop_reason="tool_use",
                model="m",
                content=[block(type="tool_use", id="tu_x", name="run_backtest", input={"symbol": "X"})],
            )
            return FakeStream([], final)
        return original(self, **kwargs)

    monkeypatch.setattr(FakeClient, "_stream", bad_stream)
    events = asyncio.run(_collect(ai_mod.chat_stream(1, "k", [{"role": "user", "content": "teste"}], None, None)))
    assert any(e["type"] == "tool_done" and not e["ok"] for e in events)
    result = FakeClient.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "INVALID_INPUT" in result["content"]


def test_chat_endpoint_streams_and_saves_report(fake_anthropic, fresh_db):
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json={"email": "ai@test.dev", "password": "12345678"}).status_code == 200
        assert client.put("/api/settings/anthropic", json={"api_key": "sk-ant-test-123456", "password": "12345678"}).status_code == 200
        with client.stream("POST", "/api/ai/chat", json={"messages": [{"role": "user", "content": "Resumo?"}], "save_report": True}) as r:
            body = "".join(r.iter_text())
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        done = [e for e in events if e["type"] == "done"]
        assert done and done[0].get("report_id")
        reports = client.get("/api/ai/reports").json()
        assert reports and client.get(f"/api/ai/reports/{reports[0]['id']}").json()["content"] == "Vou consultar.Tudo certo."


# ---------------------------------------------------------------------------
# GPT (OpenAI Responses API)


class FakeOpenAIStream:
    def __init__(self, deltas, final):
        self._deltas = deltas
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for d in self._deltas:
                yield SimpleNamespace(type="response.output_text.delta", delta=d)

        return gen()

    async def get_final_response(self):
        return self._final


class FakeAsyncOpenAI:
    """1ª resposta: texto + duas chamadas de função (uma com JSON quebrado). 2ª: só texto."""

    calls: list[dict] = []

    def __init__(self, api_key=None):
        self.responses = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        FakeAsyncOpenAI.calls.append(kwargs)
        if len(FakeAsyncOpenAI.calls) == 1:
            final = SimpleNamespace(id="resp_1", model="gpt-6-sol", status="completed", output=[
                SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="Vou consultar.")]),
                SimpleNamespace(type="function_call", call_id="call_1", name="get_portfolio", arguments='{"mode": "all"}'),
                SimpleNamespace(type="function_call", call_id="call_2", name="run_backtest", arguments='{"symbol": '),
            ])  # fmt: skip
            return FakeOpenAIStream(["Vou consultar."], final)
        final = SimpleNamespace(id="resp_2", model="gpt-6-sol", status="completed",
                                output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="Tudo certo.")])])  # fmt: skip
        return FakeOpenAIStream(["Tudo ", "certo."], final)


@pytest.fixture
def fake_openai(monkeypatch):
    FakeAsyncOpenAI.calls = []
    monkeypatch.setattr(ai_mod.openai, "AsyncOpenAI", FakeAsyncOpenAI)
    return FakeAsyncOpenAI


def test_gpt_agent_loop_runs_tools(fake_openai):
    from app.services.llm import AIConfig

    gpt = AIConfig("openai", "sk-test", "gpt-6-sol", "gpt-6-luna")
    events = asyncio.run(_collect(ai_mod.stream_chat(gpt, 1, [{"role": "user", "content": "Como estão meus bots?"}], None, None)))
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Vou consultar.Tudo certo."
    done = [e for e in events if e["type"] == "tool_done"]
    assert [d["ok"] for d in done] == [True, False]  # JSON quebrado vira erro para a IA corrigir
    assert events[-1] == {"type": "done", "model": "gpt-6-sol"}

    first, second = fake_openai.calls
    assert first["model"] == "gpt-6-sol" and first["instructions"].startswith("Você é o analista")
    assert all(t["type"] == "function" and t["strict"] is False for t in first["tools"])
    assert {t["name"] for t in first["tools"]} >= {"get_portfolio", "run_backtest", "get_news"}
    assert "previous_response_id" not in first
    # 2ª chamada continua a mesma resposta e devolve o resultado de cada função
    assert second["previous_response_id"] == "resp_1"
    outputs = {o["call_id"]: o["output"] for o in second["input"]}
    assert outputs.keys() == {"call_1", "call_2"} and "summary" in json.loads(outputs["call_1"]) and outputs["call_2"].startswith("Erro")


def test_chat_endpoint_uses_chosen_provider(fake_anthropic, fake_openai, monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm, "check_openai_key", lambda key, model: None)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"email": "ai@test.dev", "password": "12345678"}).status_code == 200
        # a chave mais recente (GPT) passa a ser a usada
        r = client.put("/api/settings/openai", json={"api_key": "sk-proj-teste-123456", "model": "gpt-6-sol", "password": "12345678"})
        assert r.status_code == 200, r.text
        status = client.get("/api/ai/status").json()
        assert status["provider"] == "openai" and status["model"] == "gpt-6-sol"
        with client.stream("POST", "/api/ai/chat", json={"messages": [{"role": "user", "content": "Resumo?"}]}) as r:
            body = "".join(r.iter_text())
        assert fake_openai.calls and not fake_anthropic.calls and '"model": "gpt-6-sol"' in body

        creds = client.get("/api/settings/credentials").json()
        assert creds["ai"]["active"] == "openai" and creds["openai"]["api_key"] == "sk-p••••3456"
        assert "sk-proj-teste-123456" not in str(creds)
        # volta para o Claude (a chave dele já estava salva)
        assert client.put("/api/settings/ai-provider", json={"provider": "anthropic"}).json()["active"] == "anthropic"
        assert client.get("/api/ai/status").json()["provider"] == "anthropic"
        # sem a chave do provedor não dá para escolher
        client.delete("/api/settings/openai")
        assert client.put("/api/settings/ai-provider", json={"provider": "openai"}).status_code == 400


def test_openai_key_needs_password_and_valid_key(monkeypatch):
    from app.services import llm

    def reject(key, model):
        raise ValueError("Chave da OpenAI inválida. Confira se copiou a chave inteira (começa com sk-).")

    monkeypatch.setattr(llm, "check_openai_key", reject)
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"email": "ai@test.dev", "password": "12345678"})
        client.delete("/api/settings/openai")  # começa sem chave da OpenAI
        body = {"api_key": "sk-proj-errada-999999", "model": "gpt-6-sol"}
        assert client.put("/api/settings/openai", json=body).status_code == 403  # sem a senha
        r = client.put("/api/settings/openai", json={**body, "password": "12345678"})
        assert r.status_code == 400 and "inválida" in r.json()["detail"]
        assert client.get("/api/settings/credentials").json()["openai"]["configured"] is False
        # nome de modelo com caracteres estranhos é recusado antes de chegar na OpenAI
        assert client.put("/api/settings/openai", json={**body, "model": "gpt 6; rm -rf", "password": "12345678"}).status_code == 422
