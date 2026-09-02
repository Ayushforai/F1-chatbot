import unittest

import app
from utils.router import CONVERSATION_MEMORY_TURNS, ROUTER_CONTEXT_TURNS, _format_history


class TestI06ConversationMemory(unittest.TestCase):
    def test_memory_keeps_last_five_turns(self):
        history = []
        for i in range(7):
            app._save_conversation_turn(
                history,
                app._make_turn(f"query {i}", "historical", f"answer {i}"),
            )
        self.assertEqual(len(history), CONVERSATION_MEMORY_TURNS)
        self.assertEqual(history[0]["query"], "query 2")
        self.assertEqual(history[-1]["query"], "query 6")

    def test_format_history_includes_answers(self):
        history = [
            {
                "query": "results of monaco gp 2021?",
                "category": "historical",
                "answer": "1. Max Verstappen (Red Bull) - ...",
            }
        ]
        text = _format_history(history)
        self.assertIn("User: results of monaco gp 2021?", text)
        self.assertIn("Assistant: 1. Max Verstappen", text)

    def test_format_history_uses_router_context_window(self):
        history = [
            {"query": f"q{i}", "category": "historical", "answer": f"a{i}"}
            for i in range(5)
        ]
        text = _format_history(history)
        self.assertNotIn("User: q0", text)
        self.assertIn("User: q2", text)
        self.assertEqual(text.count("Assistant:"), ROUTER_CONTEXT_TURNS)

    def test_follow_up_detection(self):
        history = [
            {
                "query": "results of monaco gp 2021?",
                "category": "historical",
                "answer": "1. Charles Leclerc\n2. Carlos Sainz",
            }
        ]
        self.assertTrue(app._is_answer_follow_up("who finished second?", history))
        self.assertFalse(app._is_answer_follow_up("results of monaco gp 2019?", history))

    def test_follow_up_context_uses_prior_answer(self):
        history = [
            {
                "query": "results of monaco gp 2021?",
                "answer": "P1: Verstappen",
                "category": "historical",
            }
        ]
        ctx = app._follow_up_context(history)
        self.assertIn("PREVIOUS ANSWER", ctx)
        self.assertIn("P1: Verstappen", ctx)

    def test_respond_and_remember_stores_answer(self):
        history = []
        app._respond_and_remember(
            history, "who won?", "historical", "Max Verstappen won.",
        )
        self.assertEqual(history[-1]["answer"], "Max Verstappen won.")

    def test_current_response_splits_citation(self):
        history = [
            {
                "query": "who won?",
                "category": "historical",
                "answer": "Max Verstappen won.\n\n— Source: Historical CSV — 2021",
            }
        ]
        payload = app.current_response(history)
        self.assertEqual(payload["body"], "Max Verstappen won.")
        self.assertEqual(payload["citation"], "Historical CSV — 2021")
        self.assertFalse(payload["awaiting_year"])

    def test_process_query_skips_empty(self):
        self.assertIsNone(app.process_query([], ""))

    def test_user_wants_fresh_lookup(self):
        self.assertTrue(app._user_wants_fresh_lookup("verify who finished second"))
        self.assertTrue(app._user_wants_fresh_lookup("look it up again"))
        self.assertFalse(app._user_wants_fresh_lookup("who finished second?"))

    def test_prior_answer_insufficient_for_second_place(self):
        self.assertFalse(
            app._prior_answer_likely_sufficient(
                "who finished second?",
                "The cost cap is $135 million.",
            )
        )
        self.assertTrue(
            app._prior_answer_likely_sufficient(
                "who finished second?",
                "1. Max Verstappen\n2. Charles Leclerc",
            )
        )

    def test_follow_up_lookup_uses_prior_race_context(self):
        history = [
            {
                "query": "results of monaco gp 2021?",
                "category": "historical",
                "year": 2021,
                "race_lookup_query": "results of monaco gp 2021?",
                "answer": "summary only",
            }
        ]
        lookup = app._build_follow_up_lookup_context(
            "verify who finished second", history,
        )
        self.assertIsNotNone(lookup)
        ctx, source = lookup
        self.assertIn("FRESH LOOKUP DATA", ctx)
        self.assertIn("Monaco Grand Prix", ctx)
        self.assertIn("Historical CSV", source.label)

    def test_try_follow_up_returns_none_when_lookup_unavailable(self):
        history = [
            {
                "query": "what is the cost cap?",
                "category": "financial",
                "answer": "The cost cap is $135m.",
            }
        ]
        result = app._try_answer_follow_up("verify who finished second?", history)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
