"""Moedas que a sua conta da OKX pode negociar.

A lista vem da própria OKX, pela chave cadastrada (/api/v5/account/instruments): a
OKX limita os pares por região e pelo que a conta liberou. A escolha de moedas (na
tela e no modo automático) só oferece essas. Sem chave, ou se a OKX não responder,
vale a lista pública, para nada travar.
"""

import logging
import threading
import time

from app.core.engine import make_live_trader, okx_credential
from app.db import session_scope
from app.models import Bot

log = logging.getLogger("bot_trader.tradable")

TTL = 3600
RETRY_AFTER = 300  # se a OKX não respondeu, tenta de novo logo
_cache: dict[int, tuple[float, set[str] | None]] = {}  # usuário -> (válido até, pares)
_lock = threading.Lock()

NOT_TRADABLE = "Essa moeda não está liberada na sua conta da OKX. Escolha uma da lista."


def account_symbols(user_id: int) -> set[str] | None:
    """Pares que a conta pode negociar, ou None (sem chave da OKX ou sem resposta: sem filtro)."""
    with _lock:
        hit = _cache.get(user_id)
    if hit and time.time() < hit[0]:
        return hit[1]
    symbols: set[str] | None = None
    ttl = TTL
    try:
        with session_scope() as db:
            if okx_credential(db, user_id) is None:
                return None
            trader = make_live_trader(db, Bot(user_id=user_id, mode="live"))
        symbols = trader.account_symbols() or None  # lista vazia: melhor não filtrar do que travar tudo
    except Exception as exc:
        log.info("Lista de pares da conta indisponível: %s", exc)
        ttl = RETRY_AFTER
    with _lock:
        _cache[user_id] = (time.time() + ttl, symbols)
    return symbols


def is_tradable(user_id: int, symbol: str) -> bool:
    symbols = account_symbols(user_id)
    return symbols is None or symbol.upper() in symbols


def clear_cache() -> None:
    with _lock:
        _cache.clear()
