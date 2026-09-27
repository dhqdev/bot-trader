"""Pequenos valores globais guardados no banco (tabela kv_settings)."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import KVSetting


def get_kv(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(KVSetting, key)
    return default if row is None or row.value is None else row.value


def set_kv(db: Session, key: str, value: Any) -> None:
    row = db.get(KVSetting, key)
    if row is None:
        db.add(KVSetting(key=key, value=value))
    else:
        row.value = value
