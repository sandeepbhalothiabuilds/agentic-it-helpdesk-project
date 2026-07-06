from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.backend.config import settings


def _sqlite_url() -> str:
    fallback_path = Path(settings.sqlite_fallback_path)
    return f"sqlite+pysqlite:///{fallback_path.resolve()}"


def _build_engine():
    try:
        return create_engine(settings.database_url, pool_pre_ping=True)
    except Exception:
        if not settings.sqlite_fallback_enabled:
            raise
        return create_engine(_sqlite_url(), pool_pre_ping=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
