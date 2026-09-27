"""Verificação em duas etapas (2FA) e registro de atividade da conta."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.account import audit, event_view, get_security, require_step_up
from app.db import get_db
from app.deps import get_current_user
from app.models import SecurityEvent, User
from app.schemas import StepUpIn, TwoFactorCodeIn
from app.security import (
    decrypt,
    encrypt,
    hash_recovery_code,
    new_recovery_codes,
    new_totp_secret,
    qr_data_uri,
    totp_uri,
    verify_totp,
)

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/status")
def security_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sec = get_security(db, user.id)
    db.commit()
    return {
        "two_factor": {
            "enabled": sec.totp_enabled,
            "recovery_codes_left": len(sec.recovery_codes or []) if sec.totp_enabled else 0,
        },
    }


@router.get("/events")
def security_events(limit: int = Query(50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SecurityEvent).where(SecurityEvent.user_id == user.id).order_by(SecurityEvent.id.desc()).limit(limit))
    return [event_view(e) for e in rows]


@router.post("/2fa/setup")
def setup_2fa(body: StepUpIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Gera o segredo e o QR code. Só passa a valer depois de confirmar um código (/2fa/enable)."""
    sec = get_security(db, user.id)
    if sec.totp_enabled:
        raise HTTPException(400, "A verificação em duas etapas já está ativada.")
    require_step_up(db, user, body.password, None, request, "ativar 2 etapas")
    secret = new_totp_secret()
    sec.totp_secret_enc = encrypt(secret)
    sec.totp_last_step = 0
    db.commit()
    uri = totp_uri(secret, user.email)
    return {"secret": secret, "uri": uri, "qr": qr_data_uri(uri)}


@router.post("/2fa/enable")
def enable_2fa(body: TwoFactorCodeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sec = get_security(db, user.id)
    if sec.totp_enabled:
        raise HTTPException(400, "A verificação em duas etapas já está ativada.")
    if not sec.totp_secret_enc:
        raise HTTPException(400, "Comece pela leitura do QR code.")
    step = verify_totp(decrypt(sec.totp_secret_enc), body.code, 0)
    if step is None:
        raise HTTPException(400, "Código não confere. Confira se o horário do celular está automático e digite o código atual.")
    codes = new_recovery_codes()
    sec.totp_enabled = True
    sec.totp_last_step = step
    sec.recovery_codes = [hash_recovery_code(c) for c in codes]
    audit(db, user.id, "2fa_enabled", request)
    db.commit()
    return {"ok": True, "recovery_codes": codes}


@router.post("/2fa/disable")
def disable_2fa(body: StepUpIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sec = get_security(db, user.id)
    if not sec.totp_enabled:
        raise HTTPException(400, "A verificação em duas etapas não está ativada.")
    require_step_up(db, user, body.password, body.code, request, "desativar 2 etapas")
    sec.totp_enabled = False
    sec.totp_secret_enc = None
    sec.totp_last_step = 0
    sec.recovery_codes = []
    audit(db, user.id, "2fa_disabled", request)
    db.commit()
    return {"ok": True}


@router.post("/2fa/recovery-codes")
def regenerate_codes(body: StepUpIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sec = get_security(db, user.id)
    if not sec.totp_enabled:
        raise HTTPException(400, "Ative a verificação em duas etapas primeiro.")
    require_step_up(db, user, body.password, body.code, request, "gerar códigos de recuperação")
    codes = new_recovery_codes()
    sec.recovery_codes = [hash_recovery_code(c) for c in codes]
    audit(db, user.id, "recovery_regenerated", request)
    db.commit()
    return {"ok": True, "recovery_codes": codes}
