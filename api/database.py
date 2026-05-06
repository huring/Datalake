from functools import lru_cache
from pathlib import Path
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from models import Base


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:"):
        return None

    return Path(database_url.removeprefix("sqlite:///"))


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    sqlite_path = _sqlite_path(settings.database_url)
    engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **engine_kwargs)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    Base.metadata.create_all(bind=get_engine())


def check_database_readiness() -> dict[str, object]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return {
            "status": "degraded",
            "engine": get_engine().dialect.name,
            "message": str(exc),
        }

    return {
        "status": "ok",
        "engine": get_engine().dialect.name,
    }
