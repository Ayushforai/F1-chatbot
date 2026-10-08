"""Conversation history: in-memory dict or PostgreSQL chat.* tables."""

from __future__ import annotations

import threading
from utils.db import connect, uses_postgres_sessions

_sessions: dict[str, list[dict]] = {}
_session_locks: dict[str, threading.Lock] = {}
_tables_lock = threading.Lock()


def memory_sessions() -> dict[str, list[dict]]:
    return _sessions


def memory_locks() -> dict[str, threading.Lock]:
    return _session_locks


def session_lock(session_id: str) -> threading.Lock:
    with _tables_lock:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[session_id] = lock
        return lock


def load_history(session_id: str) -> list[dict]:
    if not uses_postgres_sessions():
        with _tables_lock:
            return _sessions.setdefault(session_id, [])
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat.sessions (session_id)
            VALUES (%s)
            ON CONFLICT (session_id) DO UPDATE SET last_active_at = now()
            """,
            (session_id,),
        )
        rows = conn.execute(
            """
            SELECT payload FROM chat.turns
            WHERE session_id = %s
            ORDER BY turn_index
            """,
            (session_id,),
        ).fetchall()
    history: list[dict] = []
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, dict):
            history.append(payload)
    return history


def save_history(session_id: str, history: list[dict]) -> None:
    if not uses_postgres_sessions():
        with _tables_lock:
            _sessions[session_id] = history
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat.sessions (session_id)
            VALUES (%s)
            ON CONFLICT (session_id) DO UPDATE SET last_active_at = now()
            """,
            (session_id,),
        )
        from psycopg.types.json import Json

        conn.execute("DELETE FROM chat.turns WHERE session_id = %s", (session_id,))
        for index, turn in enumerate(history):
            conn.execute(
                """
                INSERT INTO chat.turns (session_id, turn_index, payload)
                VALUES (%s, %s, %s)
                """,
                (session_id, index, Json(turn)),
            )


def reset_session(session_id: str | None) -> None:
    if not uses_postgres_sessions():
        if session_id:
            with session_lock(session_id):
                with _tables_lock:
                    _sessions.pop(session_id, None)
                    _session_locks.pop(session_id, None)
            return
        with _tables_lock:
            session_ids = list(_session_locks.keys())
        for sid in session_ids:
            with session_lock(sid):
                with _tables_lock:
                    _sessions.pop(sid, None)
                    _session_locks.pop(sid, None)
        return

    with connect() as conn:
        if session_id:
            conn.execute("DELETE FROM chat.sessions WHERE session_id = %s", (session_id,))
        else:
            conn.execute("DELETE FROM chat.sessions")


def clear_memory_for_tests() -> None:
    _sessions.clear()
    _session_locks.clear()
