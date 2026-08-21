import unittest
from unittest.mock import patch

import app


class TestI02YearClarification(unittest.TestCase):
    def test_race_lookup_without_year_asks_before_defaulting(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": None,
            "country": "Monaco",
            "location": None,
            "lap_number": None,
        }
        result = app.resolve_query_year("fastest lap at monaco", params, [])
        self.assertEqual(result["kind"], "clarify")
        self.assertIn("Which season or year", result["message"])

    def test_race_lookup_with_explicit_year_skips_clarification(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": None,
            "country": "Monaco",
            "location": None,
            "lap_number": None,
        }
        result = app.resolve_query_year("fastest lap at monaco 2024", params, [])
        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["year"], 2024)

    def test_live_telemetry_without_year_does_not_ask(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": 1,
            "year": None,
            "country": None,
            "location": None,
            "lap_number": None,
        }
        result = app.resolve_query_year("current speed for verstappen", params, [])
        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["year"], app.DEFAULT_YEAR)

    def test_follow_up_inherits_year_from_prior_quantitative_turn(self):
        params = {
            "query_type": "specific_lap",
            "driver_number": 44,
            "year": None,
            "country": "Monaco",
            "location": None,
            "lap_number": 12,
        }
        history = [{"query": "lap 12 monaco 2024", "category": "quantitative", "year": 2024}]
        result = app.resolve_query_year("what about lap 13?", params, history)
        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["year"], 2024)

    def test_clarification_reply_with_year_uses_that_year(self):
        pending = {
            "awaiting_year": True,
            "pending_params": {
                "query_type": "fastest_lap",
                "driver_number": None,
                "country": "Monaco",
                "location": None,
                "lap_number": None,
            },
        }
        params = app._apply_pending_year_clarification("2024", pending)
        self.assertEqual(params["year"], 2024)

    def test_clarification_reply_without_year_defaults_to_2026(self):
        pending = {
            "awaiting_year": True,
            "pending_params": {
                "query_type": "fastest_lap",
                "driver_number": None,
                "country": "Monaco",
                "location": None,
                "lap_number": None,
            },
        }
        params = app._apply_pending_year_clarification("not sure", pending)
        self.assertEqual(params["year"], app.DEFAULT_YEAR)

    def test_clarification_reply_empty_string_defaults_to_2026(self):
        pending = {
            "awaiting_year": True,
            "pending_params": {
                "query_type": "fastest_lap",
                "driver_number": None,
                "country": "Monaco",
                "location": None,
                "lap_number": None,
            },
        }
        params = app._apply_pending_year_clarification("", pending)
        self.assertEqual(params["year"], app.DEFAULT_YEAR)

    def test_resolve_quantitative_uses_resolved_year_not_silent_default(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": 2023,
            "country": "Monaco",
            "location": None,
            "lap_number": None,
        }
        with patch.object(app, "get_fastest_lap_of_race", return_value={"driver": "Max Verstappen"}) as fastest:
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "context")
        fastest.assert_called_once_with(2023, "Monaco", None, location=None)

    def test_extractor_failure_no_longer_forces_year_2026(self):
        with patch("utils.router.ollama.generate", side_effect=RuntimeError("llm down")):
            from utils.router import extract_telemetry_params

            params = extract_telemetry_params("fastest lap monaco")

        self.assertIsNone(params["year"])

    def test_race_results_without_year_asks_before_defaulting(self):
        result = app.resolve_race_results_year("results of monaco gp?", [])
        self.assertEqual(result["kind"], "clarify")
        self.assertIn("Which season or year", result["message"])

    def test_race_results_with_explicit_year_skips_clarification(self):
        result = app.resolve_race_results_year("results of monaco gp 2021?", [])
        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["year"], 2021)

    def test_race_results_clarification_reply_without_year_defaults_to_2026(self):
        pending = {
            "awaiting_year": True,
            "pending_kind": "historical_race",
            "pending_query": "results of monaco gp?",
        }
        year = app._resolve_pending_year("not sure")
        self.assertEqual(year, app.DEFAULT_YEAR)
        # CSV may not have 2026 Monaco; verify the default-year path is taken.
        context_2021 = app._format_race_results_response(
            "results of monaco gp?", [], year=2021,
        )
        self.assertIn("Monaco Grand Prix", context_2021)
        context_default = app._format_race_results_response(
            pending["pending_query"], [], year=year,
        )
        self.assertIn(str(app.DEFAULT_YEAR), context_default)


if __name__ == "__main__":
    unittest.main()
