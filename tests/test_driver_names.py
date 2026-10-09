import unittest

from utils.driver_ambiguity import (
    apply_surname_ambiguity_policy,
    apply_verstappen_policy,
    mentions_jos_verstappen,
)
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

    def test_max_in_points_query_text(self):
        match = match_driver_in_text(
            "how many points did max win in the year 2023?",
            year=2023,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Max Verstappen")

    def test_surname_verstappen_defaults_to_max(self):
        match = resolve_driver_identity(ref="Verstappen", query="points in 2023", year=2023)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Max Verstappen")

    def test_jos_requires_explicit_name(self):
        self.assertTrue(mentions_jos_verstappen(query="how did jos verstappen finish in 1994"))
        jos = match_driver_ref("Jos", year=1994)
        self.assertIsNotNone(jos)
        self.assertEqual(jos["full_name"], "Jos Verstappen")
        resolved = apply_surname_ambiguity_policy(
            jos, ref="Verstappen", query="points in 1994", year=1994
        )
        self.assertEqual(resolved["full_name"], "Jos Verstappen")
        resolved_modern = apply_surname_ambiguity_policy(
            jos, ref="Verstappen", query="points in 2023", year=2023
        )
        self.assertEqual(resolved_modern["full_name"], "Max Verstappen")
        resolved_jos = apply_verstappen_policy(jos, ref="Jos", query="jos verstappen 1994", year=1994)
        self.assertEqual(resolved_jos["full_name"], "Jos Verstappen")

    def test_hamilton_surname_defaults_to_lewis_on_current_grid(self):
        match = resolve_driver_identity(ref="Hamilton", query="driver standings", year=2026)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Lewis Hamilton")

    def test_de_vries_multiword_surname(self):
        match = match_driver_in_text("lap time for de vries at spa 2023", year=2023)
        self.assertIsNotNone(match)
        self.assertEqual(match["full_name"], "Nyck de Vries")

    def test_fuzzy_hamilton_typo(self):
        match = match_driver_in_text(
            "what is hamiliton's fastest lap in the current race",
            year=2026,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["surname"], "Hamilton")


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
