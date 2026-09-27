from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.account import token_version
from app.db import get_db
from app.models import Bot, User
from app.security import COOKIE_NAME, decode_access_token


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    decoded = decode_access_token(token) if token else None
    if decoded is None:
        return None
    user_id, version = decoded
    user = db.get(User, user_id)
    # "sair de todos os dispositivos" e troca de senha aumentam a versão: tokens antigos param de valer
    if user is None or version != token_version(db, user_id):
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(request, db)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    return user


def get_user_bot(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Bot:
    bot = db.get(Bot, bot_id)
    if bot is None or bot.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot não encontrado")
    return bot
