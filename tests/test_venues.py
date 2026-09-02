import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import app
from utils.f1_api import SESSION_NOT_HELD_MESSAGE, fetch_race_session, get_fastest_lap_of_race
from utils.venues import (
    countries_in_query,
    csv_race_keyword,
    format_multi_gp_listing_answer,
    is_country_race_listing_query,
    is_multi_gp_listing_query,
    resolve_venue,
    uses_csv_country_race_listing,
)


def _response(payload, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload
    return mock


IMOLA_RACE = {
    "session_key": 9515,
    "location": "Imola",
    "circuit_short_name": "Imola",
    "date_start": "2024-05-19T13:00:00+00:00",
    "date_end": "2024-05-19T15:00:00+00:00",
}
MONZA_RACE = {
    "session_key": 9590,
    "location": "Monza",
    "circuit_short_name": "Monza",
    "date_start": "2024-09-01T13:00:00+00:00",
    "date_end": "2024-09-01T15:00:00+00:00",
}
FUTURE_RACE = {
    "session_key": 12000,
    "location": "Singapore",
    "circuit_short_name": "Marina Bay",
    "date_start": "2026-10-04T12:00:00+00:00",
    "date_end": "2026-10-04T14:00:00+00:00",
}
NOW = datetime(2026, 8, 16, 3, 0, tzinfo=timezone.utc)


class TestVenueSynonyms(unittest.TestCase):
    def test_great_britain_maps_to_united_kingdom(self):
        venue = resolve_venue(country="Great Britain", query="British GP 2024 fastest lap")
        self.assertEqual(venue["kind"], "ok")
        self.assertEqual(venue["country"], "United Kingdom")

    def test_uk_and_silverstone_synonyms(self):
        for query in ("fastest lap at Silverstone 2024", "fastest lap UK 2024", "fastest lap in England 2024"):
            venue = resolve_venue(query=query)
            self.assertEqual(venue["kind"], "ok", query)
            self.assertEqual(venue["country"], "United Kingdom", query)

    def test_abu_dhabi_maps_to_uae(self):
        venue = resolve_venue(country="Abu Dhabi", query="Abu Dhabi Grand Prix")
        self.assertEqual(venue["kind"], "ok")
        self.assertEqual(venue["country"], "United Arab Emirates")

    def test_italy_without_circuit_asks_which_gp(self):
        venue = resolve_venue(country="Italy", query="fastest lap in Italy 2024")
        self.assertEqual(venue["kind"], "clarify")
        self.assertIn("Imola", venue["message"])
        self.assertIn("Monza", venue["message"])

    def test_monza_and_imola_are_specific(self):
        monza = resolve_venue(query="fastest lap at Monza 2024")
        self.assertEqual(monza, {"kind": "ok", "country": "Italy", "location": "Monza"})
        imola = resolve_venue(query="fastest lap Imola 2024")
        self.assertEqual(imola, {"kind": "ok", "country": "Italy", "location": "Imola"})
        italian_gp = resolve_venue(query="fastest lap at the Italian Grand Prix 2024")
        self.assertEqual(italian_gp["kind"], "clarify")
        self.assertIn("Imola", italian_gp["message"])

    def test_united_states_without_circuit_asks_which_gp(self):
        venue = resolve_venue(country="United States", query="fastest lap in the USA 2024")
        self.assertEqual(venue["kind"], "clarify")
        self.assertIn("Miami", venue["message"])
        self.assertIn("Austin", venue["message"])
        self.assertIn("Las Vegas", venue["message"])

    def test_us_gp_asks_which_venue(self):
        for query in (
            "results of US gp 2023?",
            "fastest lap at the United States Grand Prix 2024",
            "results of united states gp 2024",
        ):
            venue = resolve_venue(query=query)
            self.assertEqual(venue["kind"], "clarify", query)
            self.assertIn("Miami", venue["message"], query)
            self.assertIn("Austin", venue["message"], query)

    def test_austin_and_cota_are_specific(self):
        for query in ("fastest lap at COTA 2024", "results of Austin gp 2023"):
            venue = resolve_venue(query=query)
            self.assertEqual(venue["kind"], "ok", query)
            self.assertEqual(venue["location"], "Austin", query)

    def test_miami_and_vegas_aliases(self):
        self.assertEqual(
            resolve_venue(query="Miami GP lap times"),
            {"kind": "ok", "country": "United States", "location": "Miami"},
        )
        self.assertEqual(
            resolve_venue(query="Las Vegas Grand Prix"),
            {"kind": "ok", "country": "United States", "location": "Las Vegas"},
        )

    def test_csv_keywords_follow_canonical_venues(self):
        self.assertEqual(csv_race_keyword("United Kingdom"), "British")
        self.assertEqual(csv_race_keyword("United Arab Emirates"), "Abu Dhabi")
        self.assertEqual(csv_race_keyword("Italy", "Imola"), "Emilia Romagna")
        self.assertEqual(csv_race_keyword("Italy", "Monza"), "Italian")
        self.assertEqual(csv_race_keyword("United States", "Miami"), "Miami")
        self.assertEqual(csv_race_keyword("United States", "Austin"), "United States Grand Prix")
        self.assertEqual(csv_race_keyword("United States", "Las Vegas"), "Las Vegas")
        from utils.venues import csv_race_keywords
        self.assertIn("São Paulo", csv_race_keywords("Brazil"))
        self.assertIn("Mexico City", csv_race_keywords("Mexico"))

    def test_countries_in_query_finds_italy_and_usa(self):
        countries = countries_in_query("what all races are held in italy and USA?")
        self.assertIn("Italy", countries)
        self.assertIn("United States", countries)

    def test_multi_gp_listing_query_detection(self):
        self.assertTrue(
            is_multi_gp_listing_query("what all races are held in italy and USA?")
        )
        self.assertFalse(is_multi_gp_listing_query("cost cap in 2026"))

    def test_india_listing_uses_csv_not_multi_gp_map(self):
        self.assertTrue(is_country_race_listing_query("grand prixs held in india?"))
        self.assertTrue(uses_csv_country_race_listing("grand prixs held in india?"))
        self.assertFalse(is_multi_gp_listing_query("grand prixs held in india?"))

    def test_format_multi_gp_listing_answer(self):
        answer = format_multi_gp_listing_answer("what races are held in Italy and USA?")
        self.assertIn("Monza", answer)
        self.assertIn("Imola", answer)
        self.assertIn("Miami", answer)
        self.assertIn("Las Vegas", answer)
        self.assertIn("Austin", answer)


class TestOpenF1VenueAndFutureSession(unittest.TestCase):
    def test_italy_with_monza_uses_monza_session_not_imola(self):
        def fake_get(url, params=None, **kwargs):
            params = params or {}
            if url.endswith("/sessions"):
                return _response([IMOLA_RACE, MONZA_RACE])
            if url.endswith("/laps"):
                self.assertEqual(params.get("session_key"), 9590)
                return _response([{"lap_duration": 81.0, "lap_number": 10, "driver_number": 1}])
            if url.endswith("/drivers"):
                return _response([{"full_name": "Max VERSTAPPEN"}])
            raise AssertionError(url)

        with patch("utils.f1_api.requests.get", side_effect=fake_get):
            result = get_fastest_lap_of_race(2024, "Italy", location="Monza", now=NOW)

        self.assertEqual(result["race"], "Monza 2024")
        self.assertEqual(result["driver"], "Max VERSTAPPEN")

    def test_italy_without_location_does_not_silently_pick_imola(self):
        with patch(
            "utils.f1_api.requests.get",
            return_value=_response([IMOLA_RACE, MONZA_RACE]),
        ):
            result = fetch_race_session(2024, "Italy", now=NOW)

        self.assertIn("Which Grand Prix do you mean?", result)
        self.assertIn("Monza", result)

    def test_future_session_returns_not_held_message(self):
        with patch("utils.f1_api.requests.get", return_value=_response([FUTURE_RACE])):
            result = fetch_race_session(2026, "Singapore", now=NOW)
        self.assertEqual(result, SESSION_NOT_HELD_MESSAGE)

    def test_missing_session_in_current_year_is_not_held(self):
        with patch("utils.f1_api.requests.get", return_value=_response({"detail": "No results found."}, status=404)):
            result = fetch_race_session(2026, "Singapore", now=NOW)
        self.assertEqual(result, SESSION_NOT_HELD_MESSAGE)

    def test_missing_session_in_past_year_is_not_found(self):
        with patch("utils.f1_api.requests.get", return_value=_response({"detail": "No results found."}, status=404)):
            result = fetch_race_session(2019, "Singapore", now=NOW)
        self.assertIn("Could not locate a Race session", result)
        self.assertIn("Singapore", result)
        self.assertIn("2019", result)

    def test_app_asks_which_us_gp(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": 2024,
            "country": "United States",
            "lap_number": None,
        }
        with patch.object(app, "get_fastest_lap_of_race") as fastest:
            result = app.resolve_quantitative_query(params, user_query="fastest lap in the USA 2024")
        self.assertEqual(result["kind"], "clarify")
        self.assertIn("Miami", result["message"])
        fastest.assert_not_called()

    def test_app_maps_british_gp_to_united_kingdom(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": 2024,
            "country": "Great Britain",
            "lap_number": None,
        }
        with patch.object(app, "get_fastest_lap_of_race", return_value={"driver": "Lewis HAMILTON"}) as fastest:
            result = app.resolve_quantitative_query(params, user_query="fastest lap British GP 2024")
        self.assertEqual(result["kind"], "context")
        fastest.assert_called_once_with(2024, "United Kingdom", None, location="Silverstone")

    def test_app_surfaces_future_session_error(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": 2026,
            "country": "Singapore",
            "lap_number": None,
        }
        with patch.object(app, "get_fastest_lap_of_race", return_value=SESSION_NOT_HELD_MESSAGE):
            result = app.resolve_quantitative_query(params, user_query="fastest lap Singapore 2026")
        self.assertEqual(result, {"kind": "error", "message": SESSION_NOT_HELD_MESSAGE})


if __name__ == "__main__":
    unittest.main()
