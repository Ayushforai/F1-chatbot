"""PostgreSQL connection helpers for Racecoe."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"
PGVECTOR_SCHEMA_PATH = ROOT / "db" / "schema_pgvector.sql"


def database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def historical_backend() -> str:
    """csv | postgres | auto (postgres when DATABASE_URL is set and f1.races has rows)."""
    raw = (os.getenv("HISTORICAL_BACKEND") or "csv").strip().lower()
    if raw in {"csv", "postgres", "auto"}:
        return raw
    return "csv"


def session_store() -> str:
    """memory | postgres. Default memory so chat works before schema is applied."""
    raw = (os.getenv("SESSION_STORE") or "memory").strip().lower()
    if raw in {"memory", "postgres"}:
        return raw
    return "memory"


def uses_postgres_sessions() -> bool:
    return bool(database_url()) and session_store() == "postgres"


_pg_archive_ready: bool | None = None


def reset_backend_cache() -> None:
    global _pg_archive_ready
    _pg_archive_ready = None


def uses_postgres_historical() -> bool:
    if not database_url():
        return False
    mode = historical_backend()
    if mode == "csv":
        return False
    if mode == "postgres":
        return True
    return postgres_archive_ready()


def postgres_archive_ready() -> bool:
    global _pg_archive_ready
    if _pg_archive_ready is not None:
        return _pg_archive_ready
    if not database_url():
        _pg_archive_ready = False
        return False
    try:
        with connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM f1.races").fetchone()
        _pg_archive_ready = bool(row and int(row["n"]) > 0)
    except Exception:
        _pg_archive_ready = False
    return _pg_archive_ready


@contextmanager
def connect(*, autocommit: bool = False) -> Iterator:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(normalize_database_url(url), row_factory=dict_row, autocommit=autocommit)
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


def _statements(sql_text: str) -> list[str]:
    chunks: list[str] = []
    for raw in sql_text.split(";"):
        lines = [line for line in raw.splitlines() if line.strip() and not line.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            chunks.append(stmt)
    return chunks


def apply_schema(*, include_pgvector: bool = True) -> dict:
    """Apply db/schema.sql (and optional pgvector additions)."""
    applied = {"core": False, "pgvector": False, "pgvector_error": None}
    core_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(autocommit=True) as conn:
        for stmt in _statements(core_sql):
            conn.execute(stmt)
        applied["core"] = True
        if include_pgvector and PGVECTOR_SCHEMA_PATH.is_file():
            try:
                for stmt in _statements(PGVECTOR_SCHEMA_PATH.read_text(encoding="utf-8")):
                    conn.execute(stmt)
                applied["pgvector"] = True
            except Exception as exc:
                applied["pgvector_error"] = str(exc)
    reset_backend_cache()
    return applied


def health_payload() -> dict:
    url_set = bool(database_url())
    payload = {
        "database_url_set": url_set,
        "historical_backend": historical_backend(),
        "historical_using_postgres": False,
        "session_store": session_store(),
        "sessions_using_postgres": uses_postgres_sessions(),
        "reachable": False,
        "archive_rows": None,
        "error": None,
    }
    if not url_set:
        return payload
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
            try:
                row = conn.execute("SELECT COUNT(*) AS n FROM f1.races").fetchone()
                payload["archive_rows"] = int(row["n"]) if row else 0
            except Exception:
                payload["archive_rows"] = None
        payload["reachable"] = True
        payload["historical_using_postgres"] = uses_postgres_historical()
    except Exception as exc:
        payload["error"] = str(exc)
    return payload
