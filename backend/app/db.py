from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
        pool_pre_ping=True,
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Colunas criadas depois da primeira versão. create_all só cria tabelas novas, então
# bancos antigos recebem a coluna aqui (com valor padrão para as linhas existentes).
ADDED_COLUMNS = [
    # bots anteriores à coluna eram da Binance: ficam marcados assim e engine.migrate_to_okx os passa para a OKX
    ("bots", "exchange", "VARCHAR(16) NOT NULL DEFAULT 'binance'"),
]


def _add_missing_columns(target=None) -> None:
    target = target or engine
    inspector = inspect(target)
    tables = set(inspector.get_table_names())
    with target.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            if table in tables and column not in {c["name"] for c in inspector.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    from app import models  # noqa: F401  (registra as tabelas)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sessão para uso fora das rotas (motor dos bots, ferramentas da IA)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
