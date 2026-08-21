import unittest
from unittest.mock import patch

import app
from utils.historical_db import format_driver_teams, get_driver_teams


class DriverTeamLookupTests(unittest.TestCase):
    def test_full_name_resolution(self):
        from utils.historical_db import _resolve_driver

        resolved = _resolve_driver("lance stroll")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1], "Lance Stroll")

    def test_stroll_2018_williams(self):
        result = get_driver_teams(2018, "lance stroll")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Teams"][0]["Team"], "Williams")

    def test_hamilton_2012_mclaren(self):
        result = get_driver_teams(2012, "Hamilton")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Driver"], "Lewis Hamilton")
        self.assertEqual(len(result["Teams"]), 1)
        self.assertEqual(result["Teams"][0]["Team"], "McLaren")
        self.assertEqual(result["Teams"][0]["Races"], 20)

    def test_alonso_2007_mclaren(self):
        result = get_driver_teams(2007, "Alonso")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Teams"][0]["Team"], "McLaren")

    def test_unknown_driver(self):
        result = get_driver_teams(2012, "NotADriver")
        self.assertIsInstance(result, str)
        self.assertIn("Could not find driver", result)

    def test_format_driver_teams(self):
        packet = get_driver_teams(2012, "Hamilton")
        text = format_driver_teams(packet)
        self.assertIn("2012", text)
        self.assertIn("Lewis Hamilton", text)
        self.assertIn("McLaren", text)

    def test_is_driver_team_query(self):
        self.assertTrue(app._is_driver_team_query("Which team did Hamilton drive for in 2012?"))
        self.assertFalse(app._is_driver_team_query("Results of Monaco GP 2012"))

    def test_driver_ref_from_team_query(self):
        ref = app._driver_ref_from_team_query("Which team did Hamilton drive for in 2012?")
        self.assertEqual(ref.lower(), "hamilton")

    def test_handle_driver_team_query(self):
        with patch("app.extract_telemetry_params", return_value={"driver_name": "Hamilton"}):
            history: list[dict] = []
            handled = app._handle_driver_team_query(
                history,
                "Which team did Hamilton drive for in 2012?",
            )
        self.assertTrue(handled)
        self.assertIn("McLaren", history[-1]["answer"])

    def test_handle_driver_team_query_prompts_for_year(self):
        with patch("app.extract_telemetry_params", return_value={"driver_name": "Hamilton"}):
            history: list[dict] = []
            handled = app._handle_driver_team_query(
                history,
                "Which team did Hamilton drive for?",
            )
        self.assertTrue(handled)
        self.assertTrue(history[-1].get("awaiting_year"))
        self.assertEqual(history[-1].get("pending_kind"), "driver_team")

    def test_driver_team_follow_up_year(self):
        history = [
            {
                "query": "Which team did Alonso drive for in 2018?",
                "category": "historical",
                "year": 2018,
                "driver_lookup_query": "Which team did Alonso drive for in 2018?",
                "answer": "In 2018, Fernando Alonso raced for:\n- McLaren (21 races, rounds 1–21)",
            }
        ]
        result = app._try_driver_team_follow_up("and in 2023?", history)
        self.assertIsNotNone(result)
        self.assertIn("Aston Martin", result["answer"])
        self.assertEqual(result["year"], 2023)

    def test_try_answer_follow_up_driver_team(self):
        history = [
            {
                "query": "Which team did Alonso drive for in 2018?",
                "category": "historical",
                "year": 2018,
                "driver_lookup_query": "Which team did Alonso drive for in 2018?",
                "answer": "McLaren all season.",
            }
        ]
        result = app._try_answer_follow_up("and in 2023?", history)
        self.assertIsNotNone(result)
        self.assertIn("Aston Martin", result["answer"])


if __name__ == "__main__":
    unittest.main()
