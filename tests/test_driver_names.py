import unittest

from utils.driver_names import (
    DATA_PATH as CATALOG_PATH,
    match_driver_in_text,
    match_driver_ref,
    resolve_driver_identity,
)
from utils.driver_numbers import enrich_telemetry_params


@unittest.skipUnless(CATALOG_PATH.is_file(), "F1DriversDataset.csv missing")
class TestDriverNamesCatalog(unittest.TestCase):
    def test_full_name_in_query(self):
        match = match_driver_in_text("lap 12 for lewis hamilton at monaco 2024", year=2024)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Lewis Hamilton")
        self.assertEqual(match["surname"], "Hamilton")

    def test_surname_in_query(self):
        match = match_driver_in_text("how did stroll finish at monaco 2023?", year=2023)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Lance Stroll")

    def test_disambiguates_max_toward_active_verstappen(self):
        match = match_driver_ref("Max", year=2025)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Max Verstappen")

    def test_de_vries_multiword_surname(self):
        match = match_driver_in_text("lap time for de vries at spa 2023", year=2023)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Nyck de Vries")


@unittest.skipUnless(CATALOG_PATH.is_file(), "F1DriversDataset.csv missing")
class TestDriverNamesWithNumbers(unittest.TestCase):
    def test_catalog_name_resolves_to_car_number(self):
        params = {
            "query_type": "specific_lap",
            "driver_number": None,
            "driver_name": None,
            "year": 2024,
            "country": "Monaco",
            "location": None,
            "lap_number": 12,
        }
        enriched = enrich_telemetry_params(
            params,
            "lap 12 for lewis hamilton at monaco 2024",
            year=2024,
        )
        self.assertEqual(enriched["driver_name"], "Hamilton")
        self.assertEqual(enriched["driver_number"], 44)

    def test_catalog_fills_name_when_extractor_omits_it(self):
        identity = resolve_driver_identity(query="current speed of Lance Stroll", year=2025)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["surname"], "Stroll")


if __name__ == "__main__":
    unittest.main()
