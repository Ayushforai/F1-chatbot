import unittest

import app
from utils.historical_db import get_race_results
from utils.venues import is_multi_gp_clarification, resolve_venue


class VenueClarificationFlowTests(unittest.TestCase):
    def test_race_results_query_detects_ambiguous_country(self):
        self.assertTrue(app._is_race_results_query("results of USA 2024?"))
        self.assertTrue(app._is_race_results_query("results of Italy 2024?"))

    def test_maybe_ask_for_venue_prompts_for_usa(self):
        history: list[dict] = []
        prompted = app._maybe_ask_for_venue(
            history,
            "results of USA 2024?",
            "historical",
            "historical_race",
        )
        self.assertTrue(prompted)
        self.assertTrue(history[-1].get("awaiting_venue"))
        self.assertIn("Miami", history[-1]["answer"])

    def test_resume_race_results_after_venue_reply(self):
        history = [
            {
                "query": "results of USA 2024?",
                "category": "historical",
                "awaiting_venue": True,
                "pending_kind": "historical_race",
                "pending_query": "results of USA 2024?",
                "answer": "Which Grand Prix do you mean?",
            }
        ]
        handled = app._handle_venue_clarification_resume(history, "Miami")
        self.assertTrue(handled)
        self.assertIn("Miami Grand Prix", history[-1]["answer"])

    def test_lap_comparison_prompts_for_ambiguous_country(self):
        history: list[dict] = []
        handled = app._respond_lap_comparison(
            history,
            "time delta between bottas and stroll on lap 32 of USA 2017?",
        )
        self.assertTrue(handled)
        self.assertTrue(history[-1].get("awaiting_venue"))
        self.assertEqual(history[-1]["pending_kind"], "lap_comparison")

    def test_resume_lap_comparison_after_venue_reply(self):
        history = [
            {
                "query": "time delta between bottas and stroll on lap 32 of USA 2017?",
                "category": "historical",
                "awaiting_venue": True,
                "pending_kind": "lap_comparison",
                "pending_query": "time delta between bottas and stroll on lap 32 of USA 2017?",
                "lap_number": 32,
                "drivers": ["bottas", "stroll"],
                "year": 2017,
                "answer": "Which Grand Prix do you mean?",
            }
        ]
        handled = app._handle_venue_clarification_resume(history, "Austin")
        self.assertTrue(handled)
        self.assertIn("Valtteri Bottas", history[-1]["answer"])

    def test_csv_blocks_ambiguous_multi_gp_lookup(self):
        result = get_race_results(2024, "Italy")
        self.assertTrue(is_multi_gp_clarification(result))

    def test_csv_allows_single_gp_multi_gp_country_year(self):
        result = get_race_results(2019, "Italy")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Grand Prix"], "Italian Grand Prix")

    def test_resolve_venue_from_clarification_combines_queries(self):
        pending = {"pending_query": "results of USA 2024?"}
        venue = app._resolve_venue_from_clarification("Miami", pending)
        self.assertEqual(venue["kind"], "ok")
        self.assertEqual(venue["location"], "Miami")

    def test_us_gp_results_prompts_before_csv_lookup(self):
        history: list[dict] = []
        prompted = app._maybe_ask_for_venue(
            history,
            "results of US gp 2023?",
            "historical",
            "historical_race",
        )
        self.assertTrue(prompted)
        self.assertTrue(history[-1].get("awaiting_venue"))
        self.assertIn("Austin", history[-1]["answer"])


if __name__ == "__main__":
    unittest.main()
