from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        _ensure_sqlite_columns()
        return

    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


def _ensure_sqlite_columns() -> None:
    inspector = inspect(engine)
    if "manga" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("manga")}
    statements = []
    if "category" not in existing:
        statements.append("ALTER TABLE manga ADD COLUMN category VARCHAR(255) NOT NULL DEFAULT ''")
    if "tags" not in existing:
        statements.append("ALTER TABLE manga ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
