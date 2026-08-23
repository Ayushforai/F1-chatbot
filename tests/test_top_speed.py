import unittest
from unittest.mock import patch

import app
from utils.f1_api import _lap_peak_speed_kmh, get_max_speed_trap
from utils.historical_db import format_top_speed_lookup


class TopSpeedLookupTests(unittest.TestCase):
    def test_is_top_speed_query(self):
        self.assertTrue(
            app._is_top_speed_query(
                "What was the highest speed an F1 car has ever attained?"
            )
        )
        self.assertTrue(app._is_top_speed_query("Top speed trap at Monza 2024"))
        self.assertFalse(app._is_top_speed_query("Results of Monaco GP 2021"))

    def test_parse_decade(self):
        self.assertEqual(app._parse_decade("highest top speed in 2010s?"), (2010, 2019))
        self.assertEqual(app._parse_decade("the 1990's"), (1990, 1999))
        self.assertIsNone(app._parse_decade("highest speed in 2010"))

    def test_explicit_year_ignores_decade(self):
        self.assertIsNone(app._explicit_year("highest top speed in 2010s?"))

    def test_decade_lookup_uses_bottas_baku_record(self):
        answer, source, extra = app._lookup_top_speed(
            "highest top speed in 2010s?",
            [],
        )
        self.assertEqual(extra.get("year_start"), 2010)
        self.assertEqual(extra.get("year_end"), 2019)
        self.assertIn("378", answer)
        self.assertIn("Bottas", answer)
        self.assertIn("Baku", answer)
        self.assertIsNotNone(source)
        self.assertIn("speed-trap", source.label)

    def test_decade_lookup_uses_only_speed_trap(self):
        answer, _source, _extra = app._lookup_top_speed(
            "highest top speed in 2010s?",
            [],
        )
        self.assertIn("378", answer)
        self.assertNotIn("For comparison", answer)
        self.assertNotIn("fastest-lap speed", answer.lower())

    @patch("app.get_max_speed_trap")
    def test_lookup_top_speed_uses_openf1_for_recent_gp(self, trap_fn):
        trap_fn.return_value = {
            "race": "Monza 2024",
            "measurement": "OpenF1 speed trap",
            "speed_kmh": 360.0,
            "speed_field": "st_speed",
            "speed_field_label": "speed trap",
            "driver": "Carlos Sainz",
            "driver_number": 55,
            "lap_number": 47,
        }
        answer, source, _extra = app._lookup_top_speed(
            "highest speed trap at Monza 2024",
            [],
            year=2024,
            venue={"kind": "ok", "country": "Italy", "location": "Monza"},
        )
        trap_fn.assert_called_once()
        self.assertIn("360.0 km/h", answer)
        self.assertIn("OpenF1", source.label)
        self.assertNotIn("fastest-lap speed", answer.lower())

    @patch("app.get_max_speed_trap_season")
    def test_lookup_top_speed_scans_season_without_venue(self, season_fn):
        season_fn.return_value = {
            "race": "Monza 2024 (Race)",
            "measurement": "OpenF1 speed trap",
            "speed_kmh": 355.0,
            "speed_field": "st_speed",
            "speed_field_label": "speed trap",
            "driver": "Charles Leclerc",
            "driver_number": 16,
            "lap_number": 51,
        }
        answer, source, _extra = app._lookup_top_speed(
            "highest top speed in 2024",
            [],
            year=2024,
            venue={"kind": "none"},
        )
        season_fn.assert_called_once_with(2024, driver_number=None)
        self.assertIn("355.0 km/h", answer)
        self.assertIn("OpenF1", source.label)

    def test_lap_peak_speed_prefers_highest_field(self):
        speed, field = _lap_peak_speed_kmh(
            {"st_speed": 330, "i1_speed": 341, "i2_speed": 320}
        )
        self.assertEqual(speed, 341.0)
        self.assertEqual(field, "i1_speed")

    def test_global_query_flags(self):
        self.assertTrue(app._is_global_top_speed_query("highest speed ever attained"))
        self.assertFalse(app._is_global_top_speed_query("top speed at Monza 2024"))

    def test_no_csv_fallback_when_no_trap_data(self):
        answer, source, _extra = app._lookup_top_speed(
            "highest top speed in 1990s?",
            [],
        )
        self.assertIsNone(source)
        self.assertIn("No speed-trap data", answer)
        self.assertNotIn("km/h —", answer)

    def test_format_top_speed_lookup_renders_packet(self):
        packet = {
            "measurement": "published speed-trap record",
            "speed_kmh": 378.0,
            "driver": "Valtteri Bottas",
            "year": 2016,
            "grand_prix": "European Grand Prix",
            "speed_field_label": "speed trap",
        }
        text = format_top_speed_lookup([packet], scope="all time")
        self.assertIn("378.0 km/h", text)
        self.assertIn("Bottas", text)

    @patch("app._respond_and_remember")
    def test_handle_global_top_speed_query(self, remember):
        history: list[dict] = []
        handled = app._handle_top_speed_query(
            history,
            "What was the highest speed an F1 car has ever attained?",
        )
        self.assertTrue(handled)
        remember.assert_called_once()
        answer = remember.call_args.args[3]
        self.assertIn("km/h", answer)


if __name__ == "__main__":
    unittest.main()
