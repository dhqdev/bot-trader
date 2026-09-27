"""Piloto automático: candidatas, validação (escolha x confirmação), aplicação, IA e API."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import autopilot as autopilot_api
from app.core.risk import RiskConfig
from app.db import session_scope
from app.main import app
from app.models import AIInsight, AutopilotConfig, Bot, BotEvent, OptimizationRun, User
from app.security import hash_password
from app.services import backtesting, optimizer
from app.services.llm import AIConfig

CLAUDE = AIConfig("anthropic", "sk-test", "claude-opus-5", "claude-haiku-4-5")
GPT = AIConfig("openai", "sk-test", "gpt-6-sol", "gpt-6-luna")

from .conftest import make_ohlcv

EMAIL, PASSWORD = "piloto@test.dev", "senha-do-piloto-1"


def _bot(strategy="squeeze", mode="paper", interval="4h", risk=None, autopilot="auto_paper", email="opt@test.dev") -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name="O", password_hash=hash_password(PASSWORD))
            db.add(user)
            db.flush()
        bot = Bot(user_id=user.id, name=f"{strategy}-{mode}", symbol="SOLUSDT", base_asset="SOL", quote_asset="USDT", interval=interval,
                  strategy=strategy, strategy_params={}, risk=RiskConfig(order_size_quote=50, **(risk or {})).model_dump(), mode=mode,
                  paper_initial_balance=1000, paper_balance=1000, status="running")  # fmt: skip
        db.add(bot)
        db.flush()
        db.add(AutopilotConfig(bot_id=bot.id, mode=autopilot, interval_hours=168, allow_strategy_change=True))
        return bot.id


def test_candidates_change_one_thing_and_never_sizing():
    bot = Bot(symbol="SOLUSDT", interval="4h", strategy="squeeze", strategy_params={}, risk=RiskConfig(order_size_quote=50).model_dump(), mode="paper")
    base, cands = optimizer.generate_candidates(bot, allow_strategy_change=True)
    keys = {c.key for c in cands}
    assert {"sentiment:rising", "sentiment:off", "risk:trailing=on", "strategy:ignition"} <= keys
    for c in cands:
        assert c.risk["order_size_quote"] == 50 and c.risk["sizing_mode"] == base.risk["sizing_mode"]
        assert c.risk["news_guard"] == base.risk["news_guard"] and c.risk["fee_pct"] == base.risk["fee_pct"]
        assert c.changes
        if c.kind == "param":
            assert sum(c.params[k] != base.params[k] for k in base.params) == 1 and c.risk == base.risk
        if c.kind in ("risk", "sentiment"):
            assert c.params == base.params and c.strategy == base.strategy
    _, no_switch = optimizer.generate_candidates(bot, allow_strategy_change=False)
    assert not [c for c in no_switch if c.kind == "strategy"]


def test_ai_proposals_are_validated():
    bot = Bot(symbol="SOLUSDT", interval="4h", strategy="squeeze", strategy_params={}, risk=RiskConfig(order_size_quote=50).model_dump(), mode="paper")
    base, _ = optimizer.generate_candidates(bot, True)
    prop = {"label": "combo", "reason": "r", "strategy": "", "params": [{"name": "length", "value": 999}],
            "risk": [{"name": "order_size_quote", "value": 1e6}, {"name": "stop_loss_atr_mult", "value": 2.5}]}  # fmt: skip
    c = optimizer.candidate_from_proposal(base, prop, True)
    assert c.params["length"] == 60  # limitado ao máximo do parâmetro
    assert c.risk["order_size_quote"] == 50  # tamanho da ordem é do usuário
    assert c.risk["stop_loss_atr_mult"] == 2.5 and c.source == "ai"
    no_stop = {**prop, "params": [], "risk": [{"name": "stop_loss_mode", "value": "none"}]}
    assert optimizer.candidate_from_proposal(base, no_stop, True) is None  # nunca tira o stop
    assert optimizer.candidate_from_proposal(base, {**prop, "strategy": "nao_existe"}, True) is None
    assert optimizer.candidate_from_proposal(base, {**prop, "strategy": "ignition"}, False) is None


# ---------------------------------------------------------------------------
# decisão com avaliação controlada


SCORES: dict[str, dict[str, float]] = {}


def fake_evaluate(ds, c, part):
    ret = SCORES.get(c.key, {}).get(part, SCORES.get("*", {}).get(part, -1.0))
    m = {"return_pct": ret, "drawdown_pct": -10.0, "trades": 20, "win_rate_pct": 40.0, "profit_factor": 1.2, "buy_hold_pct": 5.0}
    m["score"] = optimizer.score(m)
    return m


@pytest.fixture
def controlled(monkeypatch):
    df = make_ohlcv(400)
    monkeypatch.setattr(optimizer, "load_dataset", lambda symbol, interval, warm: optimizer.Dataset(symbol, interval, df, None, 100, 300))
    monkeypatch.setattr(optimizer, "evaluate", fake_evaluate)
    monkeypatch.setattr(optimizer, "_warm", lambda c: 30)
    SCORES.clear()
    SCORES.update({
        "base": {"in": 0, "out": 0, "full": 0},
        "sentiment:rising": {"in": 8, "out": -3, "full": 3},  # melhor na escolha, mas não se confirma
        "risk:trailing=on": {"in": 6, "out": 6, "full": 6},
    })  # fmt: skip
    return SCORES


def _run(bot_id: int, ai=None, client=None) -> OptimizationRun:
    with session_scope() as db:
        run = optimizer.start_run(db, db.get(Bot, bot_id), "manual")
        run_id = run.id
    optimizer.execute(run_id, ai, client)
    with session_scope() as db:
        return db.get(OptimizationRun, run_id)


def test_picks_candidate_confirmed_in_recent_period_and_applies_on_paper(controlled):
    bot_id = _bot()
    run = _run(bot_id)
    assert run.status == "applied", run.summary
    assert run.candidate["key"] == "risk:trailing=on"
    rising = next(t for t in run.tested if t["key"] == "sentiment:rising")
    assert rising["passed"] is False and "não confirmou no período recente" in rising["reasons"]
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        assert bot.risk["trailing_enabled"] is True and bot.risk["order_size_quote"] == 50
        assert any("Piloto automático aplicou" in e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id)))
        cfg = db.get(AutopilotConfig, bot_id)
        assert cfg.last_run_at is not None and cfg.next_run_at > cfg.last_run_at
        # desfazer volta a configuração anterior
        optimizer.revert_run(db, db.get(OptimizationRun, run.id))
    with session_scope() as db:
        assert db.get(Bot, bot_id).risk["trailing_enabled"] is False
        assert db.get(OptimizationRun, run.id).status == "reverted"


def test_live_bots_only_get_suggestions(controlled):
    bot_id = _bot(mode="live", autopilot="auto_paper")
    run = _run(bot_id)
    assert run.status == "suggested" and "autorização" in run.summary
    with session_scope() as db:
        assert db.get(Bot, bot_id).risk["trailing_enabled"] is False  # nada mudou sozinho
    # autorizado, mas troca de estratégia em bot real sempre fica para o usuário
    SCORES["risk:trailing=on"] = {"in": -1, "out": -1, "full": -1}
    SCORES["strategy:ignition"] = {"in": 9, "out": 9, "full": 9}
    bot2 = _bot(mode="live", autopilot="auto_all")
    with session_scope() as db:
        db.get(AutopilotConfig, bot2).live_authorized_at = db.get(Bot, bot2).created_at
    run = _run(bot2)
    assert run.status == "suggested" and run.candidate["key"] == "strategy:ignition"


def test_nothing_consistent_means_no_change(controlled):
    SCORES["risk:trailing=on"] = {"in": 6, "out": -2, "full": 1}
    bot_id = _bot(autopilot="suggest")
    run = _run(bot_id)
    assert run.status == "no_change" and "Mantida a configuração atual" in run.summary


def test_config_changed_by_user_blocks_old_suggestion(controlled):
    bot_id = _bot(autopilot="suggest")
    run = _run(bot_id)
    assert run.status == "suggested"
    with session_scope() as db:
        db.get(Bot, bot_id).strategy_params = {**db.get(Bot, bot_id).strategy_params, "length": 30}
    with session_scope() as db:
        with pytest.raises(optimizer.ApplyError):
            optimizer.apply_run(db, db.get(OptimizationRun, run.id))


class FakeAnalyst:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = {
            "analysis_md": "## Resumo\nTrailing ajudou.",
            "insights": [{"kind": "lesson", "text": "Em SOLUSDT 4h o trailing protegeu as altas."}],
            "proposals": [{"label": "combo", "reason": "junta duas boas", "strategy": "", "params": [],
                           "risk": [{"name": "trailing_enabled", "value": True}, {"name": "stop_loss_atr_mult", "value": 2.5}]}],
        }  # fmt: skip
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5", content=[SimpleNamespace(type="text", text=json.dumps(reply))])


def test_ai_analyst_learns_and_its_idea_can_win(controlled):
    SCORES["ai:combo"] = {"in": 10, "out": 10, "full": 10}
    client = FakeAnalyst()
    bot_id = _bot(autopilot="suggest")
    run = _run(bot_id, ai=CLAUDE, client=client)
    assert run.status == "suggested" and run.candidate["key"] == "ai:combo" and run.candidate["source"] == "ai"
    assert run.ai_notes.startswith("## Resumo") and run.ai_model == "claude-opus-5"
    sent = client.calls[0]["messages"][0]["content"]
    assert "<noticias_recentes>" in sent and '"tested"' in sent
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"
    with session_scope() as db:
        lessons = [i.text for i in db.scalars(select(AIInsight).where(AIInsight.bot_id == bot_id))]
    assert lessons == ["Em SOLUSDT 4h o trailing protegeu as altas."]
    # no ciclo seguinte a IA recebe as lições anteriores
    _run(bot_id, ai=CLAUDE, client=client)
    assert "trailing protegeu as altas" in client.calls[-1]["messages"][0]["content"]


def test_real_pipeline_runs_on_synthetic_data(monkeypatch):
    monkeypatch.setattr(backtesting, "history", lambda symbol, interval, bars: make_ohlcv(min(bars, 2200), seed=len(symbol), interval=interval))
    bot_id = _bot(strategy="donchian_breakout", interval="1h", autopilot="suggest")
    run = _run(bot_id)
    assert run.status in ("no_change", "suggested"), run.error
    assert run.tested and run.baseline["results"]["in"]["trades"] >= 0
    assert run.baseline["period"]["split"] > run.baseline["period"]["start"]


# ---------------------------------------------------------------------------
# API


@pytest.fixture
def api(fresh_db, controlled, monkeypatch):
    monkeypatch.setattr(autopilot_api, "launch", lambda run_id, ai: optimizer.execute(run_id, ai))
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
        yield c


def test_autopilot_api(api):
    bot_id = _bot(autopilot="suggest", email=EMAIL)
    overview = api.get("/api/autopilot").json()
    assert overview["bots"][0]["autopilot"]["mode"] == "suggest"

    # aplicar sozinho em bots reais exige a senha
    body = {"mode": "auto_all", "interval_hours": 72, "allow_strategy_change": False}
    assert api.put(f"/api/autopilot/bots/{bot_id}", json=body).status_code == 403
    r = api.put(f"/api/autopilot/bots/{bot_id}", json={**body, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["live_authorized"] is True and r.json()["interval_hours"] == 72
    r = api.put(f"/api/autopilot/bots/{bot_id}", json={"mode": "suggest", "interval_hours": 72})
    assert r.json()["live_authorized"] is False

    run = api.post(f"/api/autopilot/bots/{bot_id}/run").json()
    detail = api.get(f"/api/autopilot/runs/{run['id']}").json()
    assert detail["status"] == "suggested" and detail["tested"]
    assert api.post(f"/api/autopilot/runs/{run['id']}/apply").json()["status"] == "applied"
    assert api.get(f"/api/bots/{bot_id}").json()["risk"]["trailing_enabled"] is True
    assert api.post(f"/api/autopilot/runs/{run['id']}/apply").status_code == 400
    assert api.post(f"/api/autopilot/runs/{run['id']}/revert").json()["status"] == "reverted"
    assert api.get(f"/api/bots/{bot_id}").json()["risk"]["trailing_enabled"] is False

    run2 = api.post(f"/api/autopilot/bots/{bot_id}/run").json()
    assert api.post(f"/api/autopilot/runs/{run2['id']}/reject").json()["status"] == "rejected"
    assert len(api.get(f"/api/autopilot/runs?bot_id={bot_id}").json()) == 2
    assert api.get("/api/autopilot/runs/999999").status_code == 404


class FakeGPTAnalyst:
    def __init__(self):
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = {"analysis_md": "Análise do GPT.", "insights": [{"kind": "warning", "text": "Mercado lateral: menos sinais."}], "proposals": []}
        return SimpleNamespace(status="completed", model=kwargs["model"], output=[], output_text=json.dumps(reply))


def test_gpt_can_be_the_analyst(controlled):
    client = FakeGPTAnalyst()
    bot_id = _bot(autopilot="suggest")
    run = _run(bot_id, ai=GPT, client=client)
    assert run.ai_model == "gpt-6-sol" and run.ai_notes == "Análise do GPT."
    assert client.calls[0]["text"]["format"]["name"] == "analise_piloto"
    with session_scope() as db:
        assert [i.text for i in db.scalars(select(AIInsight).where(AIInsight.bot_id == bot_id))] == ["Mercado lateral: menos sinais."]
