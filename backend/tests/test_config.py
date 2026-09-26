import pytest

from app.config import Settings, _resolve_secret


def test_production_requires_secret():
    with pytest.raises(RuntimeError):
        _resolve_secret(Settings(env="production", secret_key=""))  # variável vazia na stack
    with pytest.raises(RuntimeError):
        _resolve_secret(Settings(env="production", secret_key="curta"))


def test_production_rejects_stack_placeholder():
    with pytest.raises(RuntimeError, match="exemplo"):
        _resolve_secret(Settings(env="production", secret_key="TROQUE_POR_UMA_CHAVE_ALEATORIA_COM_48_CARACTERES"))


def test_production_accepts_long_secret():
    secret = "x" * 48
    assert _resolve_secret(Settings(env="production", secret_key=secret)) == secret
