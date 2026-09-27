from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.account import audit, check_second_factor, client_ip, get_security, set_session, token_version
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, user_from_request
from app.models import User
from app.schemas import LoginIn, PasswordIn, RegisterIn, TwoFactorLoginIn
from app.security import (
    COOKIE_NAME,
    account_limiter,
    create_2fa_ticket,
    decode_2fa_ticket,
    dummy_hash,
    hash_password,
    login_limiter,
    twofa_limiter,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

TOO_MANY = "Muitas tentativas. Aguarde alguns minutos e tente de novo."


def user_view(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "created_at": user.created_at.isoformat()}


@router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    user = user_from_request(request, db)
    return {
        "has_users": has_users,
        "registration_open": not has_users or get_settings().allow_registration,
        "user": user_view(user) if user else None,
    }


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    if has_users and not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cadastro fechado.")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado.")
    user = User(email=body.email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, user.id, "register", request)
    db.commit()
    set_session(response, user.id, 0)
    return user_view(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request) or "?"
    email = body.email.strip().lower()
    if not login_limiter.check(ip) or not account_limiter.check(email):
        user = db.scalar(select(User).where(User.email == email))
        audit(db, user.id if user else None, "login_blocked", request)
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY)
    user = db.scalar(select(User).where(User.email == email))
    # com e-mail inexistente também roda o bcrypt: o tempo de resposta não revela quem tem conta
    ok = verify_password(body.password, user.password_hash if user else dummy_hash())
    if user is None or not ok:
        login_limiter.hit(ip)
        account_limiter.hit(email)
        if user is not None:
            audit(db, user.id, "login_fail", request)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")

    sec = get_security(db, user.id)
    if sec.totp_enabled:
        db.commit()
        # senha certa: falta o código do app autenticador (a sessão só é criada depois)
        return {"two_factor_required": True, "ticket": create_2fa_ticket(user.id, sec.token_version)}

    login_limiter.reset(ip)
    account_limiter.reset(email)
    audit(db, user.id, "login_ok", request)
    db.commit()
    set_session(response, user.id, sec.token_version)
    return user_view(user)


@router.post("/login/2fa")
def login_2fa(body: TwoFactorLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    decoded = decode_2fa_ticket(body.ticket)
    if decoded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A etapa de verificação expirou. Entre de novo com e-mail e senha.")
    user_id, version = decoded
    user = db.get(User, user_id)
    if user is None or version != token_version(db, user_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A etapa de verificação expirou. Entre de novo com e-mail e senha.")
    key = f"2fa:{user_id}"
    if not twofa_limiter.check(key):
        audit(db, user_id, "login_blocked", request, "códigos de 2 etapas errados demais")
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY)
    sec = get_security(db, user_id)
    used = check_second_factor(db, sec, body.code)
    if used is None:
        twofa_limiter.hit(key)
        audit(db, user_id, "login_2fa_fail", request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código inválido ou já usado. Confira o app autenticador.")
    twofa_limiter.reset(key)
    login_limiter.reset(client_ip(request) or "?")
    account_limiter.reset(user.email)
    audit(db, user_id, "login_ok", request, "com código de recuperação" if used == "recovery" else "com 2 etapas")
    if used == "recovery":
        audit(db, user_id, "recovery_used", request, f"restam {len(sec.recovery_codes or [])}")
    db.commit()
    set_session(response, user_id, sec.token_version)
    return user_view(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    user = user_from_request(request, db)
    if user is not None:
        audit(db, user.id, "logout", request)
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Derruba as sessões de todos os outros aparelhos (este continua conectado)."""
    sec = get_security(db, user.id)
    sec.token_version += 1
    audit(db, user.id, "logout_all", request)
    db.commit()
    set_session(response, user.id, sec.token_version)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_view(user)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = f"step:{user.id}"
    if not account_limiter.check(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY)
    if not verify_password(body.current_password, user.password_hash):
        account_limiter.hit(key)
        audit(db, user.id, "step_up_fail", request, "troca de senha: senha atual incorreta")
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A nova senha precisa ser diferente da atual.")
    user.password_hash = hash_password(body.new_password)
    sec = get_security(db, user.id)
    sec.token_version += 1  # sessões abertas em outros aparelhos caem
    audit(db, user.id, "password_changed", request)
    db.commit()
    set_session(response, user.id, sec.token_version)
    return {"ok": True}
