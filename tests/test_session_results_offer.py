import unittest
from unittest.mock import patch

import app
from utils.historical_db import format_qualifying_grid, get_qualifying_results
from utils.session_results import parse_session_choice, session_results_offer


class TestSessionResultsOffer(unittest.TestCase):
    def test_parse_session_choice(self):
        self.assertEqual(parse_session_choice("qualifying"), "Qualifying")
        self.assertEqual(parse_session_choice("sprint race"), "Sprint")
        self.assertEqual(parse_session_choice("no"), "decline")
        self.assertEqual(parse_session_choice("Race"), "decline")
        self.assertIsNone(parse_session_choice("who won the title in 2020"))

    def test_race_classification_answer_detection(self):
        answer = (
            "The results for the 2021 Monaco Grand Prix are as follows:\n\n"
            "Classified finishers (15):"
        )
        self.assertTrue(app._is_race_classification_answer(answer))
        self.assertFalse(app._is_race_classification_answer("No races found for 2026."))

    def test_monaco_2021_qualifying_from_csv(self):
        data = get_qualifying_results(2021, "Monaco")
        self.assertIsInstance(data, dict)
        text = format_qualifying_grid(data)
        self.assertIn("qualifying results", text.lower())
        self.assertIn("Starting grid", text)
        self.assertIn("Leclerc", text)

    @patch("app._format_race_results_response")
    @patch("app.resolve_race_results_year")
    def test_race_results_include_session_offer(self, resolve_year, format_results):
        resolve_year.return_value = {"kind": "ok", "year": 2021}
        format_results.return_value = (
            "The results for the 2021 Monaco Grand Prix are as follows:\n\n"
            "Classified finishers (15):\n1. Verstappen (Red Bull) - 1:38:56.921, 25.0 pts"
        )
        history: list[dict] = []
        handled = app._handle_race_results_query(history, "results of monaco gp 2021?")
        self.assertTrue(handled)
        self.assertIn(session_results_offer().strip(), history[-1]["answer"])
        self.assertTrue(history[-1].get("awaiting_session_choice"))

    @patch("app._format_session_results_response")
    def test_session_choice_resume_returns_qualifying(self, format_session):
        format_session.return_value = (
            "The qualifying results for the 2021 Monaco Grand Prix are as follows:",
            None,
        )
        history = [
            {
                "awaiting_session_choice": True,
                "pending_kind": "session_results",
                "year": 2021,
                "country": "Monaco",
                "location": None,
                "pending_query": "results of monaco gp 2021?",
                "answer": "race results",
            }
        ]
        app._handle_session_choice_resume(history, "qualifying")
        self.assertNotIn("awaiting_session_choice", history[-1])
        format_session.assert_called_once_with(2021, "Monaco", None, "Qualifying")

    def test_session_choice_decline(self):
        history = [
            {
                "awaiting_session_choice": True,
                "pending_kind": "session_results",
                "year": 2021,
                "country": "Monaco",
                "answer": "race results",
            }
        ]
        app._handle_session_choice_resume(history, "no")
        self.assertIn("anything else", history[-1]["answer"].lower())


if __name__ == "__main__":
    unittest.main()
