"""Provedores de IA: Claude (Anthropic) ou GPT (OpenAI).

O usuário pode cadastrar as duas chaves e escolher qual o sistema usa. Todas as
funções de IA (conversa, notícias e piloto automático) passam por aqui, então
trocar de provedor não muda nada no resto do sistema.

As chaves nunca vão para o texto enviado à IA: são usadas só para autenticar.
"""

import json
from dataclasses import dataclass
from typing import Literal

import anthropic
import openai
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.kv import get_kv
from app.models import Credential
from app.security import decrypt

Provider = Literal["anthropic", "openai"]
PROVIDERS: tuple[Provider, ...] = ("anthropic", "openai")
PROVIDER_LABELS = {"anthropic": "Claude (Anthropic)", "openai": "GPT (OpenAI)"}

# Modelos da OpenAI oferecidos na tela (set/2026). O campo aceita outro nome, se a OpenAI lançar um novo.
OPENAI_MODELS = [
    {"id": "gpt-6-sol", "label": "GPT-6 Sol: equilibrado, feito para agentes (padrão)"},
    {"id": "gpt-6-astra", "label": "GPT-6 Astra: o mais capaz, cerca de 5× mais caro"},
    {"id": "gpt-6-luna", "label": "GPT-6 Luna: o mais barato, menos preciso"},
]


@dataclass(frozen=True)
class AIConfig:
    provider: Provider
    api_key: str
    model: str  # conversa e piloto automático
    fast_model: str  # classificação das notícias

    @property
    def label(self) -> str:
        return PROVIDER_LABELS[self.provider]


class AIError(RuntimeError):
    """A IA respondeu, mas não deu para usar a resposta (recusa, resposta cortada...)."""


# ---------------------------------------------------------------------------
# Qual provedor e qual chave usar


def pref_key(user_id: int) -> str:
    return f"ai_provider:{user_id}"


def model_key(user_id: int) -> str:
    return f"openai_model:{user_id}"


def user_keys(db: Session, user_id: int) -> dict[str, str]:
    """Chaves disponíveis para o usuário: as cadastradas na tela e, na falta, as do servidor."""
    settings = get_settings()
    keys: dict[str, str] = {}
    for cred in db.scalars(select(Credential).where(Credential.user_id == user_id, Credential.provider.in_(PROVIDERS))):
        try:
            keys[cred.provider] = decrypt(cred.key_enc)
        except ValueError:
            continue
    if "anthropic" not in keys and settings.anthropic_api_key:
        keys["anthropic"] = settings.anthropic_api_key
    if "openai" not in keys and settings.openai_api_key:
        keys["openai"] = settings.openai_api_key
    return keys


def openai_model(db: Session, user_id: int | None) -> str:
    chosen = get_kv(db, model_key(user_id)) if user_id is not None else None
    return chosen or get_settings().openai_model


def config_for(db: Session, user_id: int | None, provider: str, api_key: str) -> AIConfig:
    settings = get_settings()
    if provider == "openai":
        return AIConfig("openai", api_key, openai_model(db, user_id), settings.openai_fast_model)
    return AIConfig("anthropic", api_key, settings.ai_model, settings.ai_fast_model)


def active_provider(db: Session, user_id: int, keys: dict[str, str] | None = None) -> str | None:
    """O provedor escolhido pelo usuário; se ele não tiver essa chave, o outro."""
    keys = user_keys(db, user_id) if keys is None else keys
    if not keys:
        return None
    preferred = get_kv(db, pref_key(user_id))
    if preferred in keys:
        return preferred
    return "anthropic" if "anthropic" in keys else "openai"


def resolve_ai(user_id: int) -> AIConfig | None:
    with session_scope() as db:
        keys = user_keys(db, user_id)
        provider = active_provider(db, user_id, keys)
        return config_for(db, user_id, provider, keys[provider]) if provider else None


def any_ai() -> AIConfig | None:
    """Para tarefas do sistema todo (classificar notícias): a IA do dono do sistema ou a do servidor."""
    with session_scope() as db:
        owners = sorted(set(db.scalars(select(Credential.user_id).where(Credential.provider.in_(PROVIDERS)))))
    for user_id in owners:
        cfg = resolve_ai(user_id)
        if cfg is not None:
            return cfg
    settings = get_settings()
    with session_scope() as db:
        if settings.anthropic_api_key:
            return config_for(db, None, "anthropic", settings.anthropic_api_key)
        if settings.openai_api_key:
            return config_for(db, None, "openai", settings.openai_api_key)
    return None


# ---------------------------------------------------------------------------
# Resposta em JSON com esquema garantido (notícias e piloto automático)


def _openai_refused(response) -> bool:
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", "") == "message":
            if any(getattr(part, "type", "") == "refusal" for part in item.content or []):
                return True
    return False


def structured(
    ai: AIConfig,
    system: str,
    content: str,
    schema: dict,
    name: str,
    max_tokens: int,
    fast: bool = False,
    client=None,
) -> tuple[dict, str]:
    """Pede à IA uma resposta que segue o esquema JSON. Devolve (dados, modelo que respondeu)."""
    model = ai.fast_model if fast else ai.model
    if ai.provider == "openai":
        client = client or openai.OpenAI(api_key=ai.api_key)
        response = client.responses.create(
            model=model,
            instructions=system,
            input=content,
            # modelos de raciocínio gastam tokens pensando antes de responder: folga maior
            max_output_tokens=max_tokens * 2,
            text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
            store=False,
        )
        if _openai_refused(response):
            raise AIError("a IA recusou a solicitação")
        if response.status != "completed":
            details = getattr(response, "incomplete_details", None)
            raise AIError(f"resposta da IA incompleta ({getattr(details, 'reason', None) or response.status})")
        return json.loads(response.output_text), response.model

    client = client or anthropic.Anthropic(api_key=ai.api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise AIError(f"resposta da IA incompleta ({response.stop_reason})")
    text = next((b.text for b in response.content if b.type == "text"), "{}")
    return json.loads(text), response.model


# ---------------------------------------------------------------------------
# Conferência da chave da OpenAI ao salvar


def check_openai_key(api_key: str, model: str) -> None:
    """Confere se a chave funciona e se o modelo existe para ela (a consulta não gasta créditos)."""
    client = openai.OpenAI(api_key=api_key, max_retries=1, timeout=20)
    try:
        client.models.retrieve(model)
    except openai.AuthenticationError as exc:
        raise ValueError("Chave da OpenAI inválida. Confira se copiou a chave inteira (começa com sk-).") from exc
    except openai.PermissionDeniedError as exc:
        raise ValueError("A chave da OpenAI não tem permissão para usar a API (verifique o projeto e os créditos da conta).") from exc
    except openai.NotFoundError as exc:
        raise ValueError(f"O modelo {model} não está disponível para esta chave. Escolha outro modelo.") from exc
    except openai.APIConnectionError as exc:
        raise ValueError("Não foi possível falar com a OpenAI agora. Tente de novo em instantes.") from exc


def error_message(exc: Exception, ai: AIConfig) -> str:
    """Mensagem em português para erros da API de qualquer provedor."""
    name = ai.label
    if isinstance(exc, (anthropic.AuthenticationError, openai.AuthenticationError)):
        return f"Chave da {name} inválida. Verifique em Configurações."
    if isinstance(exc, (anthropic.PermissionDeniedError, openai.PermissionDeniedError)):
        return f"A chave da {name} não tem permissão para este modelo."
    if isinstance(exc, (anthropic.NotFoundError, openai.NotFoundError)):
        return f"Modelo não encontrado: {ai.model}. Escolha outro em Configurações."
    if isinstance(exc, (anthropic.RateLimitError, openai.RateLimitError)):
        return f"Limite de uso da API da {name} atingido (ou sem créditos). Aguarde um pouco e tente de novo."
    if isinstance(exc, (anthropic.APIStatusError, openai.APIStatusError)):
        return f"Erro da API da {name} ({exc.status_code}): {getattr(exc, 'message', exc)}"
    if isinstance(exc, (anthropic.APIConnectionError, openai.APIConnectionError)):
        return f"Sem conexão com a API da {name}."
    return f"Erro na IA: {exc}"
