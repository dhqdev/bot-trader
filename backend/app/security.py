import base64
import hashlib
import hmac
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt
import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

ALGORITHM = "HS256"
COOKIE_NAME = "bt_session"
TOTP_ISSUER = "Bot Trader"


# ------------------------------------------------------------------ senhas


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


@lru_cache
def dummy_hash() -> str:
    """Hash de mentira: login com e-mail inexistente leva o mesmo tempo (não revela quem tem conta)."""
    return hash_password(secrets.token_urlsafe(16))


# ------------------------------------------------------------------ tokens


def create_access_token(user_id: int, token_version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[int, int] | None:
    """(id do usuário, versão das sessões) ou None. Tokens de 2FA não valem como sessão."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        if payload.get("purpose"):
            return None
        return int(payload["sub"]), int(payload.get("tv", 0))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def create_2fa_ticket(user_id: int, token_version: int) -> str:
    """Senha conferida, falta o código do app autenticador. Vale 5 minutos."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "tv": token_version, "purpose": "2fa", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def decode_2fa_ticket(ticket: str) -> tuple[int, int] | None:
    try:
        payload = jwt.decode(ticket, get_settings().secret_key, algorithms=[ALGORITHM])
        if payload.get("purpose") != "2fa":
            return None
        return int(payload["sub"]), int(payload.get("tv", 0))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


# ------------------------------------------------------------------ criptografia de chaves


def _fernet() -> Fernet:
    digest = hashlib.sha256(("bt-credentials:" + get_settings().secret_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Não foi possível descriptografar a chave (BT_SECRET_KEY mudou?)") from exc


def mask(value: str) -> str:
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}••••{value[-4:]}"


# ------------------------------------------------------------------ verificação em duas etapas (TOTP)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def qr_data_uri(text: str) -> str:
    return segno.make(text, error="m").svg_data_uri(scale=5, border=2)


def verify_totp(secret: str, code: str, last_step: int = 0) -> int | None:
    """Confere o código de 6 dígitos (aceita 30 s de diferença no relógio).

    Devolve o passo de tempo usado, que deve ser gravado: um código já usado
    (ou mais antigo) é recusado, então um código interceptado não serve de novo.
    """
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = datetime.now(timezone.utc)
    for offset in (0, -1, 1):
        moment = now + timedelta(seconds=30 * offset)
        if hmac.compare_digest(totp.at(moment), code):
            step = totp.timecode(moment)
            return step if step > last_step else None
    return None


_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # sem 0/o, 1/l/i


def new_recovery_codes(n: int = 10) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(n)]


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    key = ("bt-recovery:" + get_settings().secret_key).encode("utf-8")
    return hmac.new(key, normalize_recovery_code(code).encode("utf-8"), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ limites de tentativas


class LoginRateLimiter:
    """Conta falhas por chave (IP, e-mail ou usuário) numa janela de tempo.

    Só guarda chaves que falharam, e limpa as vencidas quando passam de
    MAX_KEYS: milhares de e-mails aleatórios não enchem a memória.
    """

    MAX_KEYS = 10_000

    def __init__(self, max_attempts: int = 10, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, deque[float]] = {}

    def _fresh(self, key: str, now: float) -> deque[float] | None:
        attempts = self._attempts.get(key)
        if attempts is None:
            return None
        while attempts and now - attempts[0] > self.window:
            attempts.popleft()
        if not attempts:
            del self._attempts[key]
            return None
        return attempts

    def check(self, key: str) -> bool:
        attempts = self._fresh(key, time.monotonic())
        return attempts is None or len(attempts) < self.max_attempts

    def hit(self, key: str) -> None:
        now = time.monotonic()
        if len(self._attempts) >= self.MAX_KEYS:
            for old in list(self._attempts):
                self._fresh(old, now)
            if len(self._attempts) >= self.MAX_KEYS:  # ainda cheio: descarta as mais antigas
                for old in sorted(self._attempts, key=lambda k: self._attempts[k][-1])[: self.MAX_KEYS // 10]:
                    del self._attempts[old]
        self._attempts.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)

    def clear(self) -> None:
        self._attempts.clear()


login_limiter = LoginRateLimiter()  # por IP: 10 falhas em 5 min
account_limiter = LoginRateLimiter(5, 900)  # por conta: 5 falhas em 15 min (senha ou confirmação)
twofa_limiter = LoginRateLimiter(5, 300)  # por conta: 5 códigos errados em 5 min
