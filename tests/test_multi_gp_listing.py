import unittest
from unittest.mock import patch

import app
from utils.historical_db import format_country_grand_prix_listing
from utils.router import route_query
from utils.venues import (
    is_country_race_listing_query,
    query_introduces_new_country,
    uses_csv_country_race_listing,
)


class MultiGpListingHandlerTests(unittest.TestCase):
    def test_route_query_uses_historical_not_general(self):
        self.assertEqual(
            route_query("what all races are held in italy and USA?"),
            "historical",
        )

    def test_india_listing_uses_csv_path(self):
        self.assertTrue(is_country_race_listing_query("grand prixs held in india?"))
        self.assertTrue(uses_csv_country_race_listing("grand prixs held in india?"))

    def test_india_csv_listing_includes_three_seasons(self):
        answer = format_country_grand_prix_listing("India")
        self.assertIn("Indian Grand Prix", answer)
        self.assertIn("2011", answer)
        self.assertIn("2013", answer)

    def test_new_country_is_not_treated_as_follow_up(self):
        prior = "Italy hosts 2 Formula 1 Grands Prix:\n- Emilia Romagna Grand Prix (Imola)"
        self.assertTrue(query_introduces_new_country("was there ever a race held in india?", prior))
        self.assertFalse(app._is_answer_follow_up("was there ever a race held in india?", [{"answer": prior}]))

    @patch("app._respond_and_remember")
    def test_handle_multi_gp_listing_query(self, remember):
        handled = app._handle_country_race_listing_query(
            [],
            "what all races are held in italy and USA?",
        )
        self.assertTrue(handled)
        remember.assert_called_once()
        answer = remember.call_args.args[3]
        self.assertIn("Monza", answer)
        self.assertIn("Miami", answer)
        self.assertEqual(remember.call_args.args[2], "historical")

    @patch("app._respond_and_remember")
    def test_handle_india_listing_from_csv(self, remember):
        handled = app._handle_country_race_listing_query(
            [],
            "was there ever a race held in india?",
        )
        self.assertTrue(handled)
        answer = remember.call_args.args[3]
        self.assertIn("Indian Grand Prix", answer)
        self.assertIn("2011", answer)
        self.assertIn("2013", answer)
        self.assertIn("races.csv", remember.call_args.kwargs["source"].label)


if __name__ == "__main__":
    unittest.main()
