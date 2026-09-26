"""Analista de IA (Claude) com ferramentas somente-leitura.

A IA consulta o portfólio, os bots, o mercado e roda backtests para
embasar as respostas. Ela NÃO envia ordens nem altera configurações:
as sugestões são aplicadas pelo usuário.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.core.exchange import INTERVAL_MINUTES
from app.core.risk import RiskConfig
from app.core.strategies import STRATEGIES
from app.db import session_scope
from app.models import Bot, BotEvent, Credential, Position
from app.security import decrypt
from app.services import backtesting, market_analysis, stats

log = logging.getLogger("bot_trader.ai")

MAX_STEPS = 10
FALLBACK_MODELS = {"claude-opus-5", "claude-opus-5-5", "claude-fable-5", "claude-fable-5-1"}

SYSTEM_PROMPT = """Você é o analista quantitativo do Bot Trader, um sistema pessoal de trading automatizado na Binance Spot (somente posições compradas, sem alavancagem). Responda sempre em português do Brasil.

Como o sistema funciona:
- Cada bot opera um par (ex.: SOLUSDT) num intervalo de candle, com uma estratégia e uma configuração de risco.
- A estratégia só é avaliada no fechamento do candle; stop loss, break-even, trailing stop e alvos parciais são checados a cada ~15 segundos com o preço atual.
- Modos: "paper" (simulado com preços reais, taxa e slippage) e "live" (dinheiro real).
- O backtest usa exatamente a mesma estratégia e o mesmo gerenciador de risco, executando na abertura do candle seguinte, com taxa de 0,1% e slippage de 0,05%.

Seu papel:
- Use as ferramentas para buscar dados reais antes de afirmar qualquer coisa sobre resultados, mercado ou desempenho. Não invente números.
- Ao sugerir mudanças de parâmetros, valide com run_backtest e compare com a configuração atual e com o buy & hold. Mostre os números lado a lado.
- Seja honesto sobre limitações: backtest não garante resultado futuro, poucas operações não têm significância estatística, e otimizar demais em um período gera overfitting. Prefira parâmetros que funcionam razoavelmente em períodos e pares diferentes a um ajuste perfeito em um só.
- Priorize controle de risco (drawdown, tamanho de posição, stop) antes de retorno.
- Você não executa ordens nem altera bots. Quando recomendar algo, diga exatamente quais campos o usuário deve mudar na tela do bot.
- Seja direto e organizado: comece pela conclusão, depois os dados que a sustentam. Use markdown com títulos curtos, listas e tabelas pequenas quando ajudar. Evite textos longos sem necessidade.

Isto não é recomendação de investimento; você ajuda o usuário a tomar decisões melhor informadas."""


# ---------------------------------------------------------------------------
# Ferramentas

INTERVALS = list(INTERVAL_MINUTES)
STRATEGY_KEYS = list(STRATEGIES)


class PortfolioIn(BaseModel):
    mode: Literal["all", "paper", "live"] = "all"


class BotIdIn(BaseModel):
    bot_id: int


class MarketIn(BaseModel):
    symbol: str = Field(min_length=4, max_length=32)
    interval: Literal[tuple(INTERVALS)] = "1h"  # type: ignore[valid-type]


class BacktestToolIn(BaseModel):
    symbol: str = Field(min_length=4, max_length=32)
    interval: Literal[tuple(INTERVALS)] = "1h"  # type: ignore[valid-type]
    strategy: Literal[tuple(STRATEGY_KEYS)]  # type: ignore[valid-type]
    params: dict = Field(default_factory=dict)
    risk: dict = Field(default_factory=dict)
    days: int = Field(90, ge=7, le=730)


class CompareIn(BaseModel):
    symbol: str = Field(min_length=4, max_length=32)
    interval: Literal[tuple(INTERVALS)] = "1h"  # type: ignore[valid-type]
    days: int = Field(90, ge=7, le=730)


def _tool(name: str, description: str, model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return {"name": name, "description": description, "input_schema": schema, "eager_input_streaming": True}


class _NoInput(BaseModel):
    pass


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_portfolio": PortfolioIn,
    "get_bot": BotIdIn,
    "get_market_snapshot": MarketIn,
    "list_strategies": _NoInput,
    "run_backtest": BacktestToolIn,
    "compare_strategies": CompareIn,
}

TOOLS = [
    _tool(
        "get_portfolio",
        "Resumo de todos os bots do usuário: resultado realizado e em aberto, taxa de acerto, posições abertas, "
        "resultado por estratégia e últimas operações. Use primeiro em perguntas gerais sobre desempenho.",
        PortfolioIn,
    ),
    _tool(
        "get_bot",
        "Detalhes de um bot: configuração completa (estratégia, parâmetros, risco), estatísticas, posição aberta, "
        "últimas condições avaliadas, últimas 20 operações fechadas e eventos recentes.",
        BotIdIn,
    ),
    _tool(
        "get_market_snapshot",
        "Retrato técnico atual de um par na Binance (ex.: BTCUSDT): regime de tendência, RSI, ADX, ATR%, posição em "
        "relação às EMAs 20/50/200, Supertrend, Bollinger %B e retornos recentes.",
        MarketIn,
    ),
    _tool(
        "list_strategies",
        "Lista as estratégias disponíveis com descrição e parâmetros (nome, padrão, mínimo, máximo), e a configuração "
        "de risco padrão.",
        _NoInput,
    ),
    _tool(
        "run_backtest",
        "Roda um backtest realista (taxa, slippage, stop, alvos, trailing) com dados históricos da Binance. `params` "
        "sobrescreve parâmetros da estratégia; `risk` sobrescreve campos da configuração de risco (mesmos nomes da "
        "configuração do bot). Retorna métricas (retorno, drawdown, sharpe, taxa de acerto, profit factor, buy & hold) "
        "e as últimas operações.",
        BacktestToolIn,
    ),
    _tool(
        "compare_strategies",
        "Roda todas as estratégias com parâmetros padrão no mesmo par e período e devolve um ranking. Útil para "
        "escolher a estratégia de um par. Demora alguns segundos.",
        CompareIn,
    ),
]


def _condensed_bot(summary: dict) -> dict:
    keep = ("id", "name", "symbol", "interval", "strategy", "strategy_name", "mode", "status", "running", "runtime_seconds")
    out = {k: summary[k] for k in keep}
    out["stats"] = summary["stats"]
    pos = summary.get("position")
    if pos:
        out["open_position"] = {
            k: pos.get(k)
            for k in ("entry_price", "current_price", "qty", "cost_quote", "unrealized_pnl", "unrealized_pct", "stop_price", "stop_kind", "entry_time")
        }
    sig = summary.get("last_signal") or {}
    if sig:
        out["last_evaluation"] = {
            "entry_signal": sig.get("entry"),
            "exit_signal": sig.get("exit"),
            "entry_checks": sig.get("entry_checks"),
            "values": sig.get("values"),
        }
    return out


def _run_tool(user_id: int, name: str, raw_input: dict) -> dict:
    model = TOOL_MODELS.get(name)
    if model is None:
        raise ValueError(f"Ferramenta desconhecida: {name}")
    args = model.model_validate(raw_input or {})

    if name == "get_portfolio":
        with session_scope() as db:
            d = stats.dashboard(db, user_id, args.mode)
        return {
            "summary": d["summary"],
            "by_strategy": d["by_strategy"],
            "bots": [_condensed_bot(b) for b in d["bots"]],
            "recent_trades": [
                {k: t[k] for k in ("bot_name", "symbol", "entry_price", "exit_price", "pnl_quote", "pnl_pct", "exit_reason", "exit_time")}
                for t in d["recent_trades"][:8]
            ],
        }

    if name == "get_bot":
        with session_scope() as db:
            bot = db.get(Bot, args.bot_id)
            if bot is None or bot.user_id != user_id:
                raise ValueError("Bot não encontrado.")
            summary = stats.bot_summary(db, bot)
            closed = db.scalars(
                select(Position).where(Position.bot_id == bot.id, Position.status == "closed").order_by(Position.id.desc()).limit(20)
            )
            events = db.scalars(select(BotEvent).where(BotEvent.bot_id == bot.id).order_by(BotEvent.id.desc()).limit(20))
            return {
                **{k: summary[k] for k in ("id", "name", "symbol", "interval", "strategy", "strategy_name", "strategy_params", "risk", "mode", "status", "status_reason", "running", "runtime_seconds", "paper_balance", "paper_initial_balance", "current_price", "stats", "last_error")},
                "open_position": summary["position"],
                "last_evaluation": summary["last_signal"],
                "recent_trades": [
                    {"entry_time": p.entry_time.isoformat(), "exit_time": p.exit_time.isoformat() if p.exit_time else None, "entry_price": p.entry_price, "exit_price": p.exit_price, "pnl_quote": p.pnl_quote, "pnl_pct": p.pnl_pct, "exit_reason": p.exit_reason}
                    for p in closed
                ],
                "recent_events": [f"[{e.created_at:%Y-%m-%d %H:%M}] {e.level}: {e.message}" for e in events],
            }  # fmt: skip

    if name == "get_market_snapshot":
        return market_analysis.snapshot(args.symbol.upper(), args.interval)

    if name == "list_strategies":
        return {"strategies": [s.describe() for s in STRATEGIES.values()], "default_risk": RiskConfig().model_dump()}

    if name == "run_backtest":
        risk = RiskConfig(**{**RiskConfig().model_dump(), **args.risk})
        result = backtesting.backtest(args.symbol.upper(), args.interval, args.strategy, args.params, risk, args.days)
        return {
            "request": result["request"],
            "metrics": result["metrics"],
            "last_trades": [
                {k: round(v, 6) if isinstance(v, float) else v for k, v in t.items()} for t in result["trades"][-10:]
            ],
        }

    if name == "compare_strategies":
        return {"ranking": backtesting.compare(args.symbol.upper(), args.interval, args.days)}

    raise ValueError(f"Ferramenta sem implementação: {name}")


TOOL_LABELS = {
    "get_portfolio": "Consultando o portfólio",
    "get_bot": "Lendo o bot",
    "get_market_snapshot": "Analisando o mercado",
    "list_strategies": "Listando estratégias",
    "run_backtest": "Rodando backtest",
    "compare_strategies": "Comparando estratégias",
}


# ---------------------------------------------------------------------------
# Chave e contexto


def resolve_api_key(user_id: int) -> str | None:
    with session_scope() as db:
        cred = db.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == "anthropic"))
        if cred:
            return decrypt(cred.key_enc)
    return get_settings().anthropic_api_key or None


def _context_block(user_id: int, bot_id: int | None, backtest: dict | None) -> str:
    parts = []
    if bot_id:
        with session_scope() as db:
            bot = db.get(Bot, bot_id)
            if bot and bot.user_id == user_id:
                parts.append(
                    f"O usuário está na tela do bot #{bot.id} \"{bot.name}\" ({bot.symbol} {bot.interval}, "
                    f"estratégia {bot.strategy}, modo {bot.mode}). Use get_bot com bot_id={bot.id} para os detalhes."
                )
    if backtest:
        compact = {k: backtest.get(k) for k in ("request", "metrics")}
        trades = backtest.get("trades") or []
        compact["last_trades"] = trades[-10:]
        parts.append(
            "O usuário está vendo este resultado de backtest na tela:\n```json\n"
            + json.dumps(compact, ensure_ascii=False, default=str)[:12000]
            + "\n```"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Loop do agente com streaming


async def chat_stream(user_id: int, api_key: str, messages: list[dict], bot_id: int | None, backtest: dict | None) -> AsyncIterator[dict]:
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=api_key)
    system: list[dict] = [{"type": "text", "text": SYSTEM_PROMPT}]
    context = await asyncio.to_thread(_context_block, user_id, bot_id, backtest)
    if context:
        system.append({"type": "text", "text": context})

    extra: dict = {}
    if settings.ai_model in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

    convo: list = [{"role": m["role"], "content": m["content"]} for m in messages]
    json_retries = 0

    for _ in range(MAX_STEPS):
        yield {"type": "status", "text": "Pensando…"}
        try:
            async with client.beta.messages.stream(
                model=settings.ai_model,
                max_tokens=32000,
                system=system,
                messages=convo,
                tools=TOOLS,
                cache_control={"type": "ephemeral"},
                **extra,
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield {"type": "text", "text": event.text}
                response = await stream.get_final_message()
            json_retries = 0
        except ValueError:
            # JSON de ferramenta impossível de interpretar: repete o turno (limitado)
            json_retries += 1
            if json_retries > 2:
                yield {"type": "error", "message": "A IA gerou uma chamada de ferramenta inválida. Tente novamente."}
                return
            continue
        except anthropic.AuthenticationError:
            yield {"type": "error", "message": "Chave da Anthropic inválida. Verifique em Configurações."}
            return
        except anthropic.PermissionDeniedError:
            yield {"type": "error", "message": "A chave da Anthropic não tem permissão para este modelo."}
            return
        except anthropic.NotFoundError:
            yield {"type": "error", "message": f"Modelo não encontrado: {settings.ai_model}."}
            return
        except anthropic.RateLimitError:
            yield {"type": "error", "message": "Limite de uso da API atingido. Aguarde um pouco e tente de novo."}
            return
        except anthropic.APIStatusError as exc:
            yield {"type": "error", "message": f"Erro da API da Anthropic ({exc.status_code}): {exc.message}"}
            return
        except anthropic.APIConnectionError:
            yield {"type": "error", "message": "Sem conexão com a API da Anthropic."}
            return

        if response.stop_reason == "refusal":
            yield {"type": "error", "message": "A IA recusou esta solicitação. Tente reformular a pergunta."}
            return
        if response.stop_reason == "pause_turn":
            convo.append({"role": "assistant", "content": response.content})
            continue

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            yield {"type": "done", "model": response.model}
            return
        if response.stop_reason == "max_tokens":
            yield {"type": "error", "message": "Resposta interrompida por tamanho. Tente uma pergunta mais específica."}
            return

        convo.append({"role": "assistant", "content": response.content})
        results = []
        for block in tool_uses:
            yield {"type": "tool", "name": block.name, "label": TOOL_LABELS.get(block.name, block.name), "input": block.input}
            try:
                if not isinstance(block.input, dict):
                    raise ValueError("entrada da ferramenta não é um objeto JSON")
                output = await asyncio.to_thread(_run_tool, user_id, block.name, block.input)
                content, is_error = json.dumps(output, ensure_ascii=False, default=str), False
            except ValidationError as exc:
                content, is_error = json.dumps({"INVALID_INPUT": exc.errors(include_url=False)}, default=str), True
            except Exception as exc:
                log.warning("Ferramenta %s falhou: %s", block.name, exc)
                content, is_error = f"Erro: {exc}", True
            yield {"type": "tool_done", "name": block.name, "ok": not is_error}
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        convo.append({"role": "user", "content": results})

    yield {"type": "error", "message": "A análise excedeu o limite de etapas."}
