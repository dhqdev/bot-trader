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
        assert client.put("/api/settings/anthropic", json={"api_key": "sk-ant-test-123456"}).status_code == 200
        with client.stream("POST", "/api/ai/chat", json={"messages": [{"role": "user", "content": "Resumo?"}], "save_report": True}) as r:
            body = "".join(r.iter_text())
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        done = [e for e in events if e["type"] == "done"]
        assert done and done[0].get("report_id")
        reports = client.get("/api/ai/reports").json()
        assert reports and client.get(f"/api/ai/reports/{reports[0]['id']}").json()["content"] == "Vou consultar.Tudo certo."
