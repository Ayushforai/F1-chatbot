import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app
from utils.race_schedule import (
    RACE_NOT_HELD_RESULTS_MESSAGE,
    is_future_race,
    race_results_unavailable_reason,
)
from utils.venues import resolve_venue


class TestFutureRaceResults(unittest.TestCase):
    def test_singapore_2026_is_future_in_september(self):
        now = datetime(2026, 9, 2, tzinfo=timezone.utc)
        venue = resolve_venue(query="singapore gp 2026")
        self.assertEqual(venue["kind"], "ok")
        self.assertTrue(
            is_future_race(
                2026,
                venue["country"],
                location=venue.get("location"),
                now=now,
            )
        )
        self.assertEqual(
            race_results_unavailable_reason(
                2026,
                venue["country"],
                location=venue.get("location"),
                now=now,
            ),
            RACE_NOT_HELD_RESULTS_MESSAGE,
        )

    def test_monaco_2024_is_not_future(self):
        now = datetime(2026, 9, 2, tzinfo=timezone.utc)
        venue = resolve_venue(query="monaco gp 2024")
        self.assertEqual(venue["kind"], "ok")
        self.assertFalse(
            is_future_race(
                2024,
                venue["country"],
                location=venue.get("location"),
                now=now,
            )
        )

    @patch("app._format_race_results_response")
    @patch("app.resolve_race_results_year")
    def test_race_results_handler_returns_future_message(
        self,
        resolve_year,
        format_results,
    ):
        resolve_year.return_value = {"kind": "ok", "year": 2026}
        format_results.return_value = RACE_NOT_HELD_RESULTS_MESSAGE
        history: list[dict] = []
        handled = app._handle_race_results_query(
            history,
            "results of Singapore GP 2026?",
        )
        self.assertTrue(handled)
        self.assertEqual(history[-1]["answer"], RACE_NOT_HELD_RESULTS_MESSAGE)

    @patch("app.route_query", return_value="quantitative")
    @patch("app.extract_telemetry_params")
    @patch("app.resolve_query_year")
    @patch("app.resolve_quantitative_query")
    def test_future_race_results_skip_quantitative_live_message(
        self,
        resolve_quantitative,
        resolve_year,
        extract_params,
        route_query,
    ):
        history: list[dict] = []
        with patch(
            "app._format_race_results_response",
            return_value=RACE_NOT_HELD_RESULTS_MESSAGE,
        ), patch(
            "app.resolve_race_results_year",
            return_value={"kind": "ok", "year": 2026},
        ):
            response = app.process_query(history, "results of Singapore GP 2026?")

        route_query.assert_not_called()
        resolve_quantitative.assert_not_called()
        self.assertIn(RACE_NOT_HELD_RESULTS_MESSAGE, response["answer"])


if __name__ == "__main__":
    unittest.main()
