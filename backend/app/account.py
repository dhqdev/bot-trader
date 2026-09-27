"""Segurança da conta: 2FA, versão das sessões, confirmação de ações sensíveis e registro de atividade."""

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SecurityEvent, User, UserSecurity
from app.security import (
    COOKIE_NAME,
    account_limiter,
    create_access_token,
    decrypt,
    hash_recovery_code,
    verify_password,
    verify_totp,
)

EVENT_LABELS = {
    "register": "Conta criada",
    "login_ok": "Login",
    "login_fail": "Senha incorreta no login",
    "login_blocked": "Login bloqueado por excesso de tentativas",
    "login_2fa_fail": "Código de 2 etapas incorreto no login",
    "logout": "Saiu",
    "logout_all": "Encerrou as sessões dos outros dispositivos",
    "password_changed": "Senha alterada",
    "step_up_fail": "Confirmação de senha/código falhou",
    "2fa_enabled": "Verificação em duas etapas ativada",
    "2fa_disabled": "Verificação em duas etapas desativada",
    "recovery_used": "Código de recuperação usado",
    "recovery_regenerated": "Novos códigos de recuperação gerados",
    "binance_keys_saved": "Chaves da Binance cadastradas",
    "binance_keys_rejected": "Chaves da Binance recusadas",
    "binance_keys_removed": "Chaves da Binance removidas",
    "anthropic_key_saved": "Chave da Anthropic cadastrada",
    "anthropic_key_removed": "Chave da Anthropic removida",
    "openai_key_saved": "Chave da OpenAI cadastrada",
    "openai_key_removed": "Chave da OpenAI removida",
    "ai_provider_changed": "IA usada pelo sistema alterada",
    "autopilot_live": "Piloto automático autorizado a mexer em bots reais",
}


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return ""
    return request.client.host or ""


def get_security(db: Session, user_id: int) -> UserSecurity:
    sec = db.get(UserSecurity, user_id)
    if sec is None:
        sec = UserSecurity(user_id=user_id, recovery_codes=[], token_version=0, totp_enabled=False, totp_last_step=0)
        db.add(sec)
        db.flush()
    return sec


def token_version(db: Session, user_id: int) -> int:
    sec = db.get(UserSecurity, user_id)
    return sec.token_version if sec else 0


def audit(db: Session, user_id: int | None, kind: str, request: Request | None = None, detail: str = "") -> None:
    agent = request.headers.get("user-agent", "") if request is not None else ""
    db.add(SecurityEvent(user_id=user_id, kind=kind, ip=client_ip(request)[:64], user_agent=agent[:200], detail=detail[:300]))


def prune_events(db: Session, keep_per_user: int = 500) -> None:
    for user_id in db.scalars(select(User.id)):
        cutoff = db.scalar(
            select(SecurityEvent.id)
            .where(SecurityEvent.user_id == user_id)
            .order_by(SecurityEvent.id.desc())
            .offset(keep_per_user)
            .limit(1)
        )
        if cutoff:
            db.execute(delete(SecurityEvent).where(SecurityEvent.user_id == user_id, SecurityEvent.id <= cutoff))


def set_session(response: Response, user_id: int, version: int) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id, version),
        httponly=True,
        # Strict: o navegador nunca manda o cookie em requisições vindas de outros sites
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.access_token_hours * 3600,
        path="/",
    )


def check_second_factor(db: Session, sec: UserSecurity, code: str | None) -> str | None:
    """Confere um código do app autenticador ou de recuperação.

    Devolve "totp" ou "recovery" (e já consome o código) ou None se não bater.
    """
    code = (code or "").strip()
    if not code or not sec.totp_enabled or not sec.totp_secret_enc:
        return None
    step = verify_totp(decrypt(sec.totp_secret_enc), code, sec.totp_last_step or 0)
    if step is not None:
        sec.totp_last_step = step
        return "totp"
    hashed = hash_recovery_code(code)
    codes = list(sec.recovery_codes or [])
    if hashed in codes:
        codes.remove(hashed)
        sec.recovery_codes = codes
        return "recovery"
    return None


def require_step_up(db: Session, user: User, password: str | None, code: str | None, request: Request | None, action: str) -> None:
    """Ações sensíveis pedem a senha de novo (e o código de 2 etapas, se ativado).

    Assim, alguém que pegue uma sessão aberta não consegue trocar as chaves da
    Binance, desligar o 2FA nem liberar o piloto automático em contas reais.
    """
    key = f"step:{user.id}"
    if not account_limiter.check(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde alguns minutos.")
    if not password or not verify_password(password, user.password_hash):
        account_limiter.hit(key)
        audit(db, user.id, "step_up_fail", request, f"{action}: senha incorreta")
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Senha incorreta.")
    sec = get_security(db, user.id)
    if sec.totp_enabled:
        used = check_second_factor(db, sec, code)
        if used is None:
            account_limiter.hit(key)
            audit(db, user.id, "step_up_fail", request, f"{action}: código inválido")
            db.commit()
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Código de verificação inválido ou já usado. Digite o código atual do app autenticador.",
            )
        if used == "recovery":
            audit(db, user.id, "recovery_used", request, action)
    account_limiter.reset(key)


def event_view(e: SecurityEvent) -> dict:
    return {
        "id": e.id,
        "kind": e.kind,
        "label": EVENT_LABELS.get(e.kind, e.kind),
        "ip": e.ip,
        "user_agent": e.user_agent,
        "detail": e.detail,
        "created_at": e.created_at.isoformat(),
    }
