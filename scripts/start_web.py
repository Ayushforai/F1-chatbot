"""Boot Postgres (schema + archive if empty), then run the FastAPI app.

Used as the Docker / Render CMD so `docker compose up` uses SQL by default.
Falls back to CSV + in-memory sessions if DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _wait_for_postgres(timeout_s: float = 90.0) -> bool:
    from utils.db import connect, database_url

    if not database_url():
        return False
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            with connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as exc:
            last_error = str(exc)
            print(f" [boot] Waiting for Postgres: {last_error}")
            time.sleep(2)
    print(f" [boot] Postgres not reachable: {last_error}")
    return False


def _ensure_archive() -> None:
    from utils.db import apply_schema, connect, reset_backend_cache

    applied = apply_schema(include_pgvector=True)
    print(f" [boot] Schema applied (pgvector={applied.get('pgvector')}).")
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM f1.races").fetchone()
        n = int(row["n"]) if row else 0
    if n > 0:
        print(f" [boot] Archive already loaded ({n} races).")
        reset_backend_cache()
        return

    print(" [boot] Loading historical CSVs into Postgres (first boot)...")
    sys.path.insert(0, str(ROOT / "scripts"))
    from load_ergast_to_postgres import DATA_DIR, load_archive

    counts = load_archive(DATA_DIR, apply=False)
    print(f" [boot] Archive load complete: {counts.get('f1.races', 0)} races.")
    reset_backend_cache()


def main() -> None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url and _wait_for_postgres():
        os.environ.setdefault("HISTORICAL_BACKEND", "postgres")
        os.environ.setdefault("SESSION_STORE", "postgres")
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            _ensure_archive()
        except Exception as exc:
            print(f" [boot] Archive setup failed ({exc}); falling back to CSV.")
            os.environ["HISTORICAL_BACKEND"] = "csv"
            os.environ["SESSION_STORE"] = "memory"
    else:
        print(" [boot] No Postgres; using CSV archive and in-memory sessions.")
        os.environ.setdefault("HISTORICAL_BACKEND", "csv")
        os.environ.setdefault("SESSION_STORE", "memory")

    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
