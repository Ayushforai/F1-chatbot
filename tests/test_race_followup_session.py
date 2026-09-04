import unittest
from unittest.mock import patch

import app
from utils.session_results import parse_session_choice, session_results_offer


MONACO_2021_ANSWER = (
    "The results for the 2021 Monaco Grand Prix are as follows:\n\n"
    "Classified finishers (18):\n"
    "1. Max Verstappen (Red Bull) - 1:38:56.820, 25.0 pts, fastest lap 1:12.909 on lap 70\n"
    "2. Carlos Sainz (Ferrari) - +8.968, 18.0 pts, fastest lap 1:13.447 on lap 71\n"
    "3. Lando Norris (McLaren) - +19.427, 15.0 pts, fastest lap 1:14.670 on lap 76\n"
    "4. Sergio Pérez (Red Bull) - +20.471, 12.0 pts, fastest lap 1:14.013 on lap 63\n"
    "5. Sebastian Vettel (Aston Martin) - +52.591, 10.0 pts, fastest lap 1:15.220 on lap 59"
)


class TestRaceFollowUpSessionStickiness(unittest.TestCase):
    def test_race_reply_declines_session_offer(self):
        self.assertEqual(parse_session_choice("Race"), "decline")
        self.assertEqual(parse_session_choice("the race"), "decline")

    def test_follow_up_abandons_session_choice_prompt(self):
        history = [
            {
                "query": "Results of Monaco GP 2021",
                "category": "historical",
                "answer": MONACO_2021_ANSWER + session_results_offer(),
                "year": 2021,
                "country": "Monaco",
                "race_lookup_query": "Results of Monaco GP 2021",
                "awaiting_session_choice": True,
                "pending_kind": "session_results",
                "pending_query": "Results of Monaco GP 2021",
            }
        ]
        self.assertTrue(app._should_abandon_session_choice("who was third?", history))
        self.assertFalse(app._should_abandon_session_choice("qualifying", history))

    def test_position_follow_up_uses_monaco_third_place(self):
        history = [
            {
                "query": "Results of Monaco GP 2021",
                "category": "historical",
                "answer": MONACO_2021_ANSWER + session_results_offer(),
                "year": 2021,
                "country": "Monaco",
                "race_lookup_query": "Results of Monaco GP 2021",
                "awaiting_session_choice": True,
                "pending_query": "Results of Monaco GP 2021",
            }
        ]
        result = app._try_position_follow_up("who was third?", history)
        self.assertIsNotNone(result)
        self.assertIn("Lando Norris", result["answer"])
        self.assertIn("McLaren", result["answer"])
        self.assertIn("Monaco", result["answer"])
        self.assertNotIn("Australian Grand Prix", result["answer"])

    def test_process_query_third_place_while_awaiting_session(self):
        history = [
            {
                "query": "Results of Monaco GP 2021",
                "category": "historical",
                "answer": MONACO_2021_ANSWER + session_results_offer(),
                "year": 2021,
                "country": "Monaco",
                "race_lookup_query": "Results of Monaco GP 2021",
                "awaiting_session_choice": True,
                "pending_kind": "session_results",
                "pending_query": "Results of Monaco GP 2021",
            }
        ]
        with patch.object(app, "route_query", return_value="historical"):
            payload = app.process_query(history, "who was third?")
        self.assertIsNotNone(payload)
        self.assertIn("Lando Norris", payload["body"])
        self.assertNotIn("Which session would you like", payload["body"])
        self.assertFalse(payload["awaiting_session_choice"])

    def test_decline_preserves_race_context_for_later_follow_up(self):
        history = [
            {
                "awaiting_session_choice": True,
                "pending_kind": "session_results",
                "year": 2021,
                "country": "Monaco",
                "race_lookup_query": "Results of Monaco GP 2021",
                "pending_query": "Results of Monaco GP 2021",
                "answer": MONACO_2021_ANSWER + session_results_offer(),
                "query": "Results of Monaco GP 2021",
            }
        ]
        app._handle_session_choice_resume(history, "no")
        self.assertEqual(history[-1].get("race_lookup_query"), "Results of Monaco GP 2021")
        self.assertEqual(history[-1].get("year"), 2021)
        self.assertEqual(history[-1].get("country"), "Monaco")

        # Anchor still finds the classification turn for "who finished third?"
        result = app._try_position_follow_up("who finished third?", history)
        self.assertIsNotNone(result)
        self.assertIn("Lando Norris", result["answer"])


if __name__ == "__main__":
    unittest.main()
