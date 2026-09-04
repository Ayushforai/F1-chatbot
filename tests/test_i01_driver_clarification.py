import unittest
from unittest.mock import patch

import app
from utils.router import extract_telemetry_params


class TestI01DriverClarification(unittest.TestCase):
    def test_live_telemetry_without_driver_asks_instead_of_defaulting_to_44(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": None,
            "year": 2024,
            "country": None,
            "lap_number": None,
        }
        with (
            patch.object(app, "get_driver_telemetry") as live,
            patch.object(app, "get_historical_lap") as historical,
            patch.object(app, "get_fastest_lap_of_race") as fastest,
        ):
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "clarify")
        self.assertIn("Which driver are you referring to?", result["message"])
        live.assert_not_called()
        historical.assert_not_called()
        fastest.assert_not_called()

    def test_specific_lap_without_driver_asks_instead_of_querying_44(self):
        params = {
            "query_type": "specific_lap",
            "driver_number": None,
            "year": 2024,
            "country": "Monaco",
            "lap_number": 12,
        }
        with patch.object(app, "get_historical_lap") as historical:
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "clarify")
        self.assertIn("Which driver are you referring to?", result["message"])
        historical.assert_not_called()

    def test_live_telemetry_with_driver_uses_that_number_not_44(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": 1,
            "year": 2024,
            "country": None,
            "lap_number": None,
        }
        with patch.object(app, "get_driver_telemetry", return_value={"speed": 312}) as live:
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "context")
        live.assert_called_once_with(driver_number=1)
        self.assertNotIn("#44", result["context"])

    def test_specific_lap_with_driver_uses_that_number_not_44(self):
        params = {
            "query_type": "specific_lap",
            "driver_number": 16,
            "year": 2024,
            "country": "Monaco",
            "lap_number": 12,
        }
        with patch.object(app, "get_historical_lap", return_value={"lap_number": 12}) as historical:
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "context")
        historical.assert_called_once_with(2024, "Monaco", 16, 12, location=None)

    def test_fastest_lap_without_driver_still_queries_overall_fastest(self):
        params = {
            "query_type": "fastest_lap",
            "driver_number": None,
            "year": 2024,
            "country": "Monaco",
            "lap_number": None,
        }
        with patch.object(app, "get_fastest_lap_of_race", return_value={"driver": "Lando Norris"}) as fastest:
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "context")
        fastest.assert_called_once_with(2024, "Monaco", None, location=None)

    def test_extractor_failure_no_longer_forces_driver_44(self):
        with patch("utils.router.llm_generate", side_effect=RuntimeError("llm down")):
            params = extract_telemetry_params("what is the current speed?")

        self.assertIsNone(params["driver_number"])


if __name__ == "__main__":
    unittest.main()
