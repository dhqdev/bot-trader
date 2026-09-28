"""Taxa real da conta na OKX.

A OKX cobra taxas diferentes por conta, nível e região: contas do Brasil no nível
Lv1, por exemplo, pagam 0,1% em ordens limitadas e 0,4% em ordens a mercado. Os
robôs enviam ordens a mercado, então os testes, a escolha dos robôs e o simulado
usam a taxa "taker" da conta, lida na própria OKX. Sem chave da OKX (ou se ela não
responder), vale a taxa padrão do RiskConfig.
"""

import logging
import threading
import time

from app.core.engine import make_live_trader, okx_credential
from app.db import session_scope
from app.models import Bot

log = logging.getLogger("bot_trader.fees")

TTL = 6 * 3600  # a taxa só muda com o nível da conta
_cache: dict[tuple[int, str], tuple[float, float]] = {}
_lock = threading.Lock()


def account_fee_pct(user_id: int, symbol: str) -> float | None:
    """Taxa (em %) que a conta paga numa ordem a mercado no par, ou None sem chave da OKX."""
    key = (user_id, symbol.upper())
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        with session_scope() as db:
            if okx_credential(db, user_id) is None:
                return None
            trader = make_live_trader(db, Bot(user_id=user_id, mode="live"))
        fee = trader.taker_fee_pct(key[1])
    except Exception as exc:
        log.info("Taxa da OKX indisponível para %s: %s", symbol, exc)
        return None
    with _lock:
        _cache[key] = (time.time(), fee)
    return fee


def clear_cache() -> None:
    with _lock:
        _cache.clear()
