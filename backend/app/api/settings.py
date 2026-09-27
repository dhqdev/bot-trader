from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.account import audit, require_step_up
from app.config import get_settings
from app.core import exchange
from app.core.exchange import BinanceTrader
from app.db import get_db
from app.deps import get_current_user
from app.kv import get_kv, set_kv
from app.models import Bot, Credential, User, utcnow
from app.schemas import AIProviderIn, AnthropicKeyIn, BinanceKeysIn, OpenAIKeyIn, OpenAIModelIn
from app.security import decrypt, encrypt, mask
from app.services import llm

router = APIRouter(prefix="/settings", tags=["settings"])


def _get(db: Session, user_id: int, provider: str) -> Credential | None:
    return db.scalar(select(Credential).where(Credential.user_id == user_id, Credential.provider == provider))


def _masked(cred: Credential | None) -> str | None:
    if cred is None:
        return None
    try:
        return mask(decrypt(cred.key_enc))
    except ValueError:
        return "(ilegível: refaça o cadastro)"


def key_review(perms: dict | None) -> tuple[list[str], list[str]]:
    """(motivos para recusar, avisos) a partir das permissões da chave na Binance."""
    if perms is None:
        return [], []
    errors, warnings = [], []
    if perms.get("withdrawals"):
        errors.append(
            "Esta chave permite SAQUE. Por segurança o sistema não aceita: crie outra chave na Binance "
            "sem a opção de saque (Enable Withdrawals desligado)."
        )
    if not perms.get("spot_trading"):
        warnings.append("A chave não tem permissão de Spot Trading: bots em modo real não vão conseguir comprar e vender.")
    if not perms.get("ip_restricted"):
        warnings.append("A chave aceita acesso de qualquer IP. Na Binance, restrinja ao IP do servidor para mais segurança.")
    if perms.get("universal_transfer") or perms.get("internal_transfer"):
        warnings.append("A chave permite transferências entre carteiras/subcontas. O sistema não precisa disso: desligue se puder.")
    if perms.get("margin") or perms.get("futures"):
        warnings.append("A chave tem margem/futuros liberados. O sistema só opera Spot: desligue o que não usa.")
    return errors, warnings


def _perm_key(user_id: int) -> str:
    return f"binance_key_check:{user_id}"


def _ai_view(db: Session, user: User, provider: str) -> dict:
    settings = get_settings()
    cred = _get(db, user.id, provider)
    env_key = bool(settings.anthropic_api_key if provider == "anthropic" else settings.openai_api_key)
    view = {
        "configured": cred is not None or env_key,
        "api_key": _masked(cred) if cred else ("(variável de ambiente)" if env_key else None),
        "source": "db" if cred else ("env" if env_key else None),
    }
    if provider == "anthropic":
        view["model"] = settings.ai_model
    else:
        view.update(model=llm.openai_model(db, user.id), fast_model=settings.openai_fast_model, models=llm.OPENAI_MODELS)
    return view


@router.get("/credentials")
def credentials(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    binance = _get(db, user.id, "binance")
    check = get_kv(db, _perm_key(user.id)) if binance else None
    active = llm.active_provider(db, user.id)
    return {
        "binance": {
            "configured": binance is not None,
            "api_key": _masked(binance),
            "testnet": binance.testnet if binance else False,
            "updated_at": binance.updated_at.isoformat() if binance else None,
            "permissions": (check or {}).get("permissions"),
            "warnings": (check or {}).get("warnings", []),
            "checked_at": (check or {}).get("checked_at"),
        },
        "anthropic": _ai_view(db, user, "anthropic"),
        "openai": _ai_view(db, user, "openai"),
        "ai": {"active": active, "active_label": llm.PROVIDER_LABELS.get(active) if active else None, "labels": llm.PROVIDER_LABELS},
    }


@router.put("/binance")
def save_binance(body: BinanceKeysIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_step_up(db, user, body.password, body.code, request, "cadastrar chaves da Binance")
    key, secret = body.api_key.strip(), body.api_secret.strip()
    try:
        info = exchange.inspect_api_key(key, secret, body.testnet)
    except Exception as exc:
        audit(db, user.id, "binance_keys_rejected", request, f"falha ao validar: {exc}"[:300])
        db.commit()
        raise HTTPException(400, f"Não foi possível validar a chave na Binance: {exc}") from exc
    errors, warnings = key_review(info.get("permissions"))
    if errors:
        audit(db, user.id, "binance_keys_rejected", request, "chave com permissão de saque")
        db.commit()
        raise HTTPException(400, " ".join(errors))

    cred = _get(db, user.id, "binance") or Credential(user_id=user.id, provider="binance")
    cred.key_enc = encrypt(key)
    cred.secret_enc = encrypt(secret)
    cred.testnet = body.testnet
    db.add(cred)
    set_kv(db, _perm_key(user.id), {"permissions": info.get("permissions"), "warnings": warnings, "checked_at": utcnow().isoformat()})
    audit(db, user.id, "binance_keys_saved", request, "testnet" if body.testnet else "")
    db.commit()
    return {"ok": True, "warnings": warnings, "permissions": info.get("permissions")}


@router.delete("/binance")
def delete_binance(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    live_running = db.scalar(select(Bot).where(Bot.user_id == user.id, Bot.mode == "live", Bot.status == "running"))
    if live_running:
        raise HTTPException(400, "Pare os bots em modo real antes de remover as chaves.")
    cred = _get(db, user.id, "binance")
    if cred:
        db.delete(cred)
        set_kv(db, _perm_key(user.id), None)
        audit(db, user.id, "binance_keys_removed", request)
        db.commit()
    return {"ok": True}


@router.post("/binance/test")
def test_binance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "binance")
    if cred is None:
        raise HTTPException(400, "Cadastre as chaves primeiro.")
    try:
        trader = BinanceTrader(decrypt(cred.key_enc), decrypt(cred.secret_enc or ""), testnet=cred.testnet)
        summary = trader.account_summary()
        permissions = trader.api_permissions()
    except Exception as exc:
        raise HTTPException(400, f"Falha ao conectar: {exc}") from exc
    errors, warnings = key_review(permissions)
    set_kv(db, _perm_key(user.id), {"permissions": permissions, "warnings": errors + warnings, "checked_at": utcnow().isoformat()})
    db.commit()
    summary["balances"] = sorted(summary["balances"], key=lambda b: b["free"] + b["locked"], reverse=True)[:20]
    return {"ok": True, "testnet": cred.testnet, "key_permissions": permissions, "warnings": errors + warnings, **summary}


@router.put("/anthropic")
def save_anthropic(body: AnthropicKeyIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_step_up(db, user, body.password, body.code, request, "cadastrar chave da Anthropic")
    cred = _get(db, user.id, "anthropic") or Credential(user_id=user.id, provider="anthropic")
    cred.key_enc = encrypt(body.api_key.strip())
    db.add(cred)
    set_kv(db, llm.pref_key(user.id), "anthropic")  # a chave mais recente passa a ser a usada
    audit(db, user.id, "anthropic_key_saved", request)
    db.commit()
    return {"ok": True}


@router.delete("/anthropic")
def delete_anthropic(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "anthropic")
    if cred:
        db.delete(cred)
        audit(db, user.id, "anthropic_key_removed", request)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- GPT (OpenAI)


@router.put("/openai")
def save_openai(body: OpenAIKeyIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_step_up(db, user, body.password, body.code, request, "cadastrar chave da OpenAI")
    key = body.api_key.strip()
    model = body.model or llm.openai_model(db, user.id)
    try:
        llm.check_openai_key(key, model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    cred = _get(db, user.id, "openai") or Credential(user_id=user.id, provider="openai")
    cred.key_enc = encrypt(key)
    db.add(cred)
    set_kv(db, llm.model_key(user.id), model)
    set_kv(db, llm.pref_key(user.id), "openai")  # a chave mais recente passa a ser a usada
    audit(db, user.id, "openai_key_saved", request, model)
    db.commit()
    return {"ok": True, "model": model}


@router.put("/openai/model")
def set_openai_model(body: OpenAIModelIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = llm.user_keys(db, user.id)
    if "openai" not in keys:
        raise HTTPException(400, "Cadastre a chave da OpenAI primeiro.")
    try:
        llm.check_openai_key(keys["openai"], body.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    set_kv(db, llm.model_key(user.id), body.model)
    db.commit()
    return {"ok": True, "model": body.model}


@router.delete("/openai")
def delete_openai(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = _get(db, user.id, "openai")
    if cred:
        db.delete(cred)
        audit(db, user.id, "openai_key_removed", request)
        db.commit()
    return {"ok": True}


@router.put("/ai-provider")
def choose_ai(body: AIProviderIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Qual IA o sistema usa (conversa, notícias e piloto automático) quando as duas chaves existem."""
    if body.provider not in llm.user_keys(db, user.id):
        raise HTTPException(400, f"Cadastre a chave da {llm.PROVIDER_LABELS[body.provider]} primeiro.")
    set_kv(db, llm.pref_key(user.id), body.provider)
    audit(db, user.id, "ai_provider_changed", request, llm.PROVIDER_LABELS[body.provider])
    db.commit()
    return {"ok": True, "active": body.provider}

