"""Database engine, session and bulk helpers."""

from __future__ import annotations

import io
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def copy_frame(df: pd.DataFrame, table: str) -> None:
    """Bulk-load a frame with PostgreSQL COPY; columns must match the table."""
    if df.empty:
        return
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)
    columns = ", ".join(f'"{c}"' for c in df.columns)
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            with cur.copy(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as copy:
                copy.write(buffer.getvalue())
        raw.commit()
    finally:
        raw.close()


def read_sql(sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def get_setting(key: str, default: str | None = None) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).first()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO settings (key, value) VALUES (:k, :v) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ),
            {"k": key, "v": value},
        )
