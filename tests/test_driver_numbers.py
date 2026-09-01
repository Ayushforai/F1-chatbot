import unittest
from unittest.mock import patch

from utils.driver_numbers import (
    DATA_PATH,
    enrich_telemetry_params,
    resolve_driver_from_query,
    resolve_driver_number,
)
from utils.router import extract_telemetry_params


@unittest.skipUnless(DATA_PATH.is_file(), "run setup_driver_numbers.py first")
class TestDriverNumbers(unittest.TestCase):
    def test_resolve_surname_2025(self):
        self.assertEqual(resolve_driver_number("Verstappen", year=2025), 1)
        self.assertEqual(resolve_driver_number("Norris", year=2025), 4)

    def test_resolve_car_number_token(self):
        self.assertEqual(resolve_driver_number("#44", year=2025), 44)

    def test_resolve_from_query_text(self):
        self.assertEqual(
            resolve_driver_from_query("current speed of Verstappen", year=2025),
            1,
        )

    def test_enrich_fills_number_from_name(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": None,
            "driver_name": "Norris",
            "year": 2025,
        }
        enriched = enrich_telemetry_params(params, "live telemetry for Norris")
        self.assertEqual(enriched["driver_number"], 4)

    def test_enrich_fills_from_query_when_extractor_failed(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": None,
            "driver_name": None,
            "year": 2025,
        }
        enriched = enrich_telemetry_params(
            params,
            "what is the current speed of Verstappen?",
            year=2025,
        )
        self.assertEqual(enriched["driver_number"], 1)
        self.assertEqual(enriched["driver_name"], "Verstappen")

    def test_extractor_failure_resolves_driver_from_query(self):
        with patch("utils.router.ollama.generate", side_effect=RuntimeError("llm down")):
            params = extract_telemetry_params(
                "what is the current speed of Verstappen?",
            )
        # default_season in driver_numbers.json is the current grid (2026 → #3)
        self.assertEqual(params["driver_number"], 3)
        self.assertEqual(params["driver_name"], "Verstappen")


if __name__ == "__main__":
    unittest.main()
