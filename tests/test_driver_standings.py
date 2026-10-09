import unittest
from unittest.mock import patch

import app
from utils.historical_db import _resolve_driver, format_driver_standing, get_driver_standing


class DriverStandingLookupTests(unittest.TestCase):
    def test_hamilton_2012_standing(self):
        result = get_driver_standing(2012, "Hamilton")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Driver"], "Lewis Hamilton")
        self.assertEqual(result["Position"], 4)
        self.assertEqual(result["Points"], 190.0)
        self.assertEqual(result["Wins"], 4)

    def test_format_driver_standing(self):
        packet = get_driver_standing(2012, "Hamilton")
        text = format_driver_standing(packet)
        self.assertIn("4th", text)
        self.assertIn("190", text)
        self.assertIn("4 race wins", text)

    def test_is_driver_standing_query(self):
        self.assertTrue(
            app._is_driver_standing_query(
                "Where did Hamilton finish in the 2012 driver standings?"
            )
        )
        self.assertTrue(
            app._is_driver_standing_query(
                "where did he finish in the driver standings in that year?"
            )
        )
        self.assertFalse(app._is_driver_standing_query("Results of Monaco GP 2012"))

    def test_handle_driver_standing_query(self):
        history: list[dict] = []
        handled = app._handle_driver_standing_query(
            history,
            "Where did Hamilton finish in the 2012 driver standings?",
        )
        self.assertTrue(handled)
        self.assertIn("4th", history[-1]["answer"])
        self.assertIn("190", history[-1]["answer"])

    def test_max_points_2023_standing_query(self):
        history: list[dict] = []
        handled = app._handle_driver_standing_query(
            history,
            "how many points did max win in the year 2023?",
        )
        self.assertTrue(handled)
        self.assertIn("Verstappen", history[-1]["answer"])
        self.assertNotIn("Jos Verstappen", history[-1]["answer"])
        self.assertIn("575", history[-1]["answer"])

    def test_driver_ref_from_standing_skips_llm(self):
        with patch("app.extract_telemetry_params") as extract:
            ref = app._driver_ref_from_standing_query(
                "how many points did max verstappen received in the year 2023?",
            )
            extract.assert_not_called()
        self.assertEqual(ref, "Verstappen")

    def test_verstappen_slug_resolves_to_max_without_jos(self):
        resolved = _resolve_driver("Verstappen", year=2023, query="how many points did max win in 2023?")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1], "Max Verstappen")

    def test_jos_verstappen_when_explicit(self):
        result = get_driver_standing(1994, "Verstappen", query="jos verstappen championship 1994")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Driver"], "Jos Verstappen")

    def test_standing_follow_up_after_driver_team(self):
        history = [
            {
                "query": "Which team did Hamilton drive for in 2012?",
                "category": "historical",
                "year": 2012,
                "driver_lookup_query": "Which team did Hamilton drive for in 2012?",
                "answer": "In 2012, Lewis Hamilton raced for:\n- McLaren (20 races, rounds 1–20)",
            }
        ]
        result = app._try_driver_standing_follow_up(
            "where did he finish in the driver standings in that year?",
            history,
        )
        self.assertIsNotNone(result)
        self.assertIn("4th", result["answer"])
        self.assertIn("190", result["answer"])
        self.assertEqual(result["year"], 2012)

    def test_try_answer_follow_up_uses_standing_not_llm(self):
        history = [
            {
                "query": "Which team did Hamilton drive for in 2012?",
                "category": "historical",
                "year": 2012,
                "driver_lookup_query": "Which team did Hamilton drive for in 2012?",
                "answer": "In 2012, Lewis Hamilton raced for:\n- McLaren (20 races, rounds 1–20)",
            }
        ]
        result = app._try_answer_follow_up(
            "where did he finish in the driver standings in that year?",
            history,
        )
        self.assertIsNotNone(result)
        self.assertIn("4th", result["answer"])
        self.assertIn("driver_standings.csv", result["source"].label)


if __name__ == "__main__":
    unittest.main()
