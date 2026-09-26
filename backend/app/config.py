"""Configuração central, lida de variáveis de ambiente (ou de backend/.env)."""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="BT_",
        extra="ignore",
    )

    env: str = "development"  # development | production
    secret_key: str = DEFAULT_SECRET  # assina os tokens e criptografa as chaves salvas
    database_url: str = ""
    access_token_hours: int = 24 * 7
    allow_registration: bool = False  # o primeiro usuário sempre pode se registrar
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False  # True em produção atrás de HTTPS
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    engine_autostart: bool = True  # retoma os bots ao iniciar o servidor
    engine_poll_seconds: int = 15  # frequência de checagem de stops/preço

    anthropic_api_key: str = ""  # opcional, também pode ser salva pela interface
    ai_model: str = "claude-opus-5"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def _resolve_secret(settings: Settings) -> str:
    secret = settings.secret_key.strip()
    if secret and secret != DEFAULT_SECRET:
        if settings.is_production and len(secret) < 32:
            raise RuntimeError("BT_SECRET_KEY muito curta: use pelo menos 32 caracteres aleatórios.")
        return secret
    if settings.is_production:
        raise RuntimeError("Defina BT_SECRET_KEY em produção.")
    # Em desenvolvimento, gera e persiste um segredo para que as chaves
    # criptografadas continuem legíveis entre reinícios.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = DATA_DIR / ".secret_key"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return secret_file.read_text(encoding="utf-8").strip()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.secret_key = _resolve_secret(settings)
    if not settings.database_url:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.database_url = f"sqlite:///{(DATA_DIR / 'bot_trader.db').as_posix()}"
    return settings
