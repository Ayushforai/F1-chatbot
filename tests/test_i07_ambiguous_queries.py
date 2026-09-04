import unittest
from unittest.mock import patch

from utils.router import (
    CAPABILITIES_MENU,
    ambiguous_query_response,
    get_ambiguous_query_response,
    is_ambiguous_query,
    is_capabilities_request,
    route_query,
)


class AmbiguousQueryTests(unittest.TestCase):
    def test_capabilities_request_shows_menu(self):
        self.assertTrue(is_capabilities_request("what can you do?"))
        response = ambiguous_query_response("help")
        self.assertIn("Race results", response)
        self.assertEqual(response, CAPABILITIES_MENU)

    def test_vague_single_word_is_ambiguous(self):
        self.assertTrue(is_ambiguous_query("f1"))
        self.assertTrue(is_ambiguous_query("telemetry"))
        self.assertIsNotNone(get_ambiguous_query_response("stats"))

    def test_specific_race_query_is_not_ambiguous(self):
        self.assertFalse(is_ambiguous_query("results of Monaco GP 2019"))
        self.assertFalse(is_ambiguous_query("fastest lap at Silverstone 2024"))

    def test_specific_rules_query_is_not_ambiguous(self):
        self.assertFalse(is_ambiguous_query("what is the cost cap in 2024?"))
        self.assertFalse(is_ambiguous_query("safety car rules"))

    def test_follow_up_with_history_is_not_ambiguous(self):
        history = [{"query": "results of monaco gp 2019?", "category": "historical", "answer": "..."}]
        self.assertFalse(is_ambiguous_query("2024", history))
        self.assertFalse(is_ambiguous_query("who finished second?", history))

    def test_ambiguous_prompt_asks_for_specificity(self):
        response = get_ambiguous_query_response("f1")
        self.assertIn("more specific", response.lower())
        self.assertIn("Race results", response)

    def test_route_query_returns_ambiguous_on_invalid_llm_output(self):
        with patch("utils.router.llm_generate", return_value={"response": "unclear category guess"}):
            self.assertEqual(route_query("something odd"), "ambiguous")

    def test_route_query_returns_ambiguous_on_router_error(self):
        with patch("utils.router.llm_generate", side_effect=RuntimeError("llm down")):
            self.assertEqual(route_query("anything"), "ambiguous")


if __name__ == "__main__":
    unittest.main()
