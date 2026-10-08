import os
import unittest
from unittest.mock import patch

from utils.db import (
    _statements,
    historical_backend,
    normalize_database_url,
    session_store,
    uses_postgres_historical,
    uses_postgres_sessions,
)


class TestPostgresConfig(unittest.TestCase):
    def test_schema_splits_into_statements(self):
        stmts = _statements("CREATE SCHEMA f1;\n-- comment\nCREATE TABLE f1.t (id int);")
        self.assertEqual(len(stmts), 2)
        self.assertIn("CREATE SCHEMA f1", stmts[0])

    def test_normalize_heroku_style_url(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host/db"),
            "postgresql://user:pass@host/db",
        )

    def test_defaults_are_auto_and_idle_without_database_url(self):
        env = {
            "HISTORICAL_BACKEND": "auto",
            "SESSION_STORE": "auto",
            "DATABASE_URL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(historical_backend(), "auto")
            self.assertEqual(session_store(), "auto")
            self.assertFalse(uses_postgres_historical())
            self.assertFalse(uses_postgres_sessions())

    def test_explicit_csv_and_memory_disable_postgres(self):
        env = {
            "HISTORICAL_BACKEND": "csv",
            "SESSION_STORE": "memory",
            "DATABASE_URL": "postgresql://localhost/racecoe",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertFalse(uses_postgres_historical())
            self.assertFalse(uses_postgres_sessions())

    def test_sessions_require_explicit_flag(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/racecoe", "SESSION_STORE": "memory"},
            clear=False,
        ):
            self.assertFalse(uses_postgres_sessions())
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/racecoe", "SESSION_STORE": "postgres"},
            clear=False,
        ):
            self.assertTrue(uses_postgres_sessions())

    def test_historical_postgres_flag_needs_url(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "", "HISTORICAL_BACKEND": "postgres"},
            clear=False,
        ):
            self.assertFalse(uses_postgres_historical())


class TestErgastColumnMap(unittest.TestCase):
    def test_results_map_includes_rank_and_status(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parent.parent / "scripts" / "load_ergast_to_postgres.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"rank": "fastest_lap_rank"', text)
        self.assertIn('"statusId": "status_id"', text)
        self.assertIn('"time": "race_time"', text)


if __name__ == "__main__":
    unittest.main()
