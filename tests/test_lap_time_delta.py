import unittest

from app import (
    _extract_two_drivers,
    _is_lap_comparison_query,
    _lap_number_from_query,
    _race_context_from_history,
    _race_context_from_query,
    _resolve_lap_comparison_race_context,
    _try_lap_comparison_lookup,
)
from utils.historical_db import format_lap_time_delta, get_lap_time_delta


class LapTimeDeltaTests(unittest.TestCase):
    def test_is_lap_comparison_query(self):
        self.assertTrue(
            _is_lap_comparison_query(
                "time delta between bottas and stroll on lap 32 of this race?"
            )
        )
        self.assertFalse(_is_lap_comparison_query("fastest lap of stroll in this race?"))

    def test_extract_two_drivers(self):
        self.assertEqual(
            _extract_two_drivers("time delta between bottas and stroll on lap 32"),
            ("bottas", "stroll"),
        )

    def test_lap_number_from_query(self):
        self.assertEqual(_lap_number_from_query("on lap 32 of this race"), 32)

    def test_get_lap_time_delta_2017_azerbaijan(self):
        result = get_lap_time_delta(2017, "Azerbaijan", "Bottas", "Stroll", 32)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Year"], 2017)
        self.assertEqual(result["Lap"], 32)
        self.assertEqual(result["Driver A"]["Name"], "Valtteri Bottas")
        self.assertEqual(result["Driver B"]["Name"], "Lance Stroll")
        self.assertEqual(result["Driver A"]["Lap Time"], "1:45.884")
        self.assertEqual(result["Driver B"]["Lap Time"], "1:46.492")
        self.assertAlmostEqual(result["Delta Seconds"], 0.608, places=3)
        self.assertEqual(result["Faster Driver"], "Valtteri Bottas")

    def test_format_lap_time_delta(self):
        packet = get_lap_time_delta(2017, "Azerbaijan", "Bottas", "Stroll", 32)
        text = format_lap_time_delta(packet)
        self.assertIn("2017 Azerbaijan Grand Prix", text)
        self.assertIn("1:45.884", text)
        self.assertIn("0.608s faster", text)

    def test_try_lap_comparison_lookup_from_history(self):
        history = [
            {
                "query": "2017",
                "pending_query": "results of azerbaijan gp?",
                "year": 2017,
                "race_lookup_query": "results of azerbaijan gp?",
                "category": "historical",
            }
        ]
        answer = _try_lap_comparison_lookup(
            "time delta between bottas and stroll on lap 32 of this race?",
            history,
        )
        self.assertIsNotNone(answer)
        self.assertIn("Valtteri Bottas", answer)
        self.assertIn("0.608s faster", answer)

    def test_race_context_from_query(self):
        ctx = _race_context_from_query(
            "time delta between bottas and stroll on lap 32 of azerbaijan gp 2017?"
        )
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["year"], 2017)
        self.assertEqual(ctx["country"], "Azerbaijan")

    def test_try_lap_comparison_lookup_standalone_query(self):
        answer = _try_lap_comparison_lookup(
            "time delta between bottas and stroll on lap 32 of azerbaijan gp 2017?",
            [],
        )
        self.assertIsNotNone(answer)
        self.assertIn("Valtteri Bottas", answer)
        self.assertIn("0.608s faster", answer)

    def test_resolve_lap_comparison_prefers_explicit_query(self):
        history = [
            {
                "query": "2017",
                "pending_query": "results of monaco gp?",
                "year": 2017,
                "race_lookup_query": "results of monaco gp?",
            }
        ]
        ctx = _resolve_lap_comparison_race_context(
            "time delta between bottas and stroll on lap 32 of azerbaijan gp 2017?",
            history,
        )
        self.assertEqual(ctx["country"], "Azerbaijan")

    def test_race_context_from_history_skips_non_race_turn(self):
        history = [
            {
                "query": "2017",
                "pending_query": "results of azerbaijan gp?",
                "year": 2017,
                "race_lookup_query": "results of azerbaijan gp?",
            },
            {
                "query": "fastest lap of stroll in this race?",
                "category": "historical",
                "answer": "Lance Stroll ... lap 44.",
            },
        ]
        ctx = _race_context_from_history(history)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["year"], 2017)


if __name__ == "__main__":
    unittest.main()
