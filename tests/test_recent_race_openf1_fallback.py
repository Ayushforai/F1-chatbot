import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app
from utils.race_schedule import RACE_NOT_HELD_RESULTS_MESSAGE


class TestRecentRaceOpenF1Fallback(unittest.TestCase):
    def test_china_2026_uses_openf1_when_csv_misses(self):
        openf1_packet = {
            "Year": 2026,
            "Grand Prix": "Chinese Grand Prix",
            "Session": "Race",
            "Classification": [
                {
                    "Position": "1",
                    "Driver": "Kimi ANTONELLI",
                    "Team": "Mercedes",
                    "Gap / Race Time": "1:42:15.123",
                    "Status": "Finished",
                    "Fastest Lap": "N/A",
                    "Fastest Lap Number": "N/A",
                    "Points": 0,
                }
            ],
        }
        with patch("app._csv_historical_record", return_value=None), patch(
            "app.get_openf1_session_classification",
            return_value=openf1_packet,
        ) as openf1:
            answer, source = app._resolve_race_results(
                "Results of Chinese GP 2026",
                [],
                2026,
            )

        openf1.assert_called_once_with(
            2026,
            "China",
            session_name="Race",
            location=None,
        )
        self.assertIn("Chinese Grand Prix", answer)
        self.assertIn("ANTONELLI", answer)
        self.assertIsNotNone(source)
        self.assertIn("OpenF1", source.label)

    def test_future_race_does_not_call_openf1(self):
        with patch(
            "app.race_results_unavailable_reason",
            return_value=RACE_NOT_HELD_RESULTS_MESSAGE,
        ), patch("app.get_openf1_session_classification") as openf1:
            answer, source = app._resolve_race_results(
                "Results of Singapore GP 2026",
                [],
                2026,
            )

        openf1.assert_not_called()
        self.assertEqual(answer, RACE_NOT_HELD_RESULTS_MESSAGE)
        self.assertIsNone(source)

    def test_csv_hit_skips_openf1(self):
        csv_text = (
            "The results for the 2021 Monaco Grand Prix are as follows:\n\n"
            "Classified finishers (1):\n1. Verstappen (Red Bull) - 1:38:56.921, 25.0 pts"
        )
        with patch("app._csv_historical_record", return_value=csv_text), patch(
            "app.get_openf1_session_classification",
        ) as openf1:
            answer, source = app._resolve_race_results(
                "results of monaco gp 2021?",
                [],
                2021,
            )

        openf1.assert_not_called()
        self.assertEqual(answer, csv_text)
        self.assertIsNotNone(source)
        self.assertIn("CSV", source.label)


if __name__ == "__main__":
    unittest.main()
