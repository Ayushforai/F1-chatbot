"""OpenF1 practice/qualifying fastest-lap lookups."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ["F1_SKIP_WARMUP"] = "1"

import app
from utils.f1_api import (
    fetch_latest_session,
    format_fastest_lap_lookup,
    get_fastest_lap_for_session,
    parse_openf1_session_name,
    query_asks_fastest_lap,
    query_asks_latest_session,
)

FP2_SESSION = {
    "session_key": 11363,
    "session_name": "Practice 2",
    "session_type": "Practice",
    "location": "Madrid",
    "country_name": "Spain",
    "year": 2026,
    "date_start": "2026-09-11T15:00:00+00:00",
    "date_end": "2026-09-11T16:00:00+00:00",
}

FASTEST_LAP_PACKET = {
    "session_label": "2026 Madrid, Spain (Practice 2)",
    "session_name": "Practice 2",
    "driver": "Lewis Hamilton",
    "driver_number": 44,
    "lap_number": 14,
    "lap_time": "1:23.939",
    "lap_time_seconds": 83.939,
}


class TestSessionNameParsing(unittest.TestCase):
    def test_parse_fp2(self):
        self.assertEqual(
            parse_openf1_session_name("fastest lap in the latest fp2 session"),
            "Practice 2",
        )

    def test_parse_qualifying(self):
        self.assertEqual(parse_openf1_session_name("qualifying times"), "Qualifying")

    def test_latest_and_fastest_flags(self):
        query = "what was the fastest lap of Hamilton in the latest fp2 session?"
        self.assertTrue(query_asks_fastest_lap(query))
        self.assertTrue(query_asks_latest_session(query))


class TestSessionFastestLapHandler(unittest.TestCase):
    def test_handle_latest_fp2_without_llm_router(self):
        history: list[dict] = []
        query = "what was the fastest lap of lewis hamilton in the latest fp2 session?"

        with patch("app.fetch_latest_session", return_value=FP2_SESSION), patch(
            "app.get_fastest_lap_for_session",
            return_value=dict(FASTEST_LAP_PACKET),
        ), patch("app.route_query") as route_mock, patch(
            "app.llm_generate"
        ) as llm_mock:
            result = app.process_query(history, query)

        route_mock.assert_not_called()
        llm_mock.assert_not_called()
        self.assertIsNotNone(result)
        self.assertIn("1:23.939", result["body"])
        self.assertIn("Practice 2", result["body"])
        self.assertEqual(result["category"], "quantitative")

    def test_format_fastest_lap_lookup(self):
        text = format_fastest_lap_lookup(FASTEST_LAP_PACKET)
        self.assertIn("Lewis Hamilton", text)
        self.assertIn("1:23.939", text)


class TestFetchLatestSession(unittest.TestCase):
    def test_fetch_latest_session_uses_session_key_latest(self):
        response = unittest.mock.MagicMock()
        response.status_code = 200
        response.json.return_value = [FP2_SESSION]

        with patch("utils.f1_api._http_get", return_value=response) as http_mock:
            session = fetch_latest_session("Practice 2")

        self.assertEqual(session["session_key"], 11363)
        http_mock.assert_called_once()
        self.assertEqual(http_mock.call_args.kwargs["params"], {"session_key": "latest"})


if __name__ == "__main__":
    unittest.main()
