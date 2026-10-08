"""Apply Racecoe SQL schema to DATABASE_URL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from utils.db import apply_schema, database_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply db/schema.sql to DATABASE_URL.")
    parser.add_argument(
        "--skip-pgvector",
        action="store_true",
        help="Do not run db/schema_pgvector.sql (vanilla Postgres).",
    )
    args = parser.parse_args()
    if not database_url():
        print("DATABASE_URL is not set. Copy .env.example and set it, or export it.")
        return 1
    result = apply_schema(include_pgvector=not args.skip_pgvector)
    print("Applied core schema.")
    if result["pgvector"]:
        print("Applied pgvector columns.")
    elif result["pgvector_error"]:
        print(f"Skipped pgvector (FAISS remains the RAG store): {result['pgvector_error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
