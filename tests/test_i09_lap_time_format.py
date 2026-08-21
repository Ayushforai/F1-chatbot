import unittest
from unittest.mock import MagicMock, patch

from utils.f1_api import format_lap_time, get_fastest_lap_of_race, get_historical_lap


def _response(payload, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload
    return mock


SESSION = {
    "session_key": 9500,
    "location": "Monza",
    "circuit_short_name": "Monza",
    "date_start": "2024-09-01T13:00:00+00:00",
    "date_end": "2024-09-01T15:00:00+00:00",
}


class TestI09LapTimeFormat(unittest.TestCase):
    def test_format_lap_time_under_one_minute(self):
        self.assertEqual(format_lap_time(58.321), "58.321")

    def test_format_lap_time_over_one_minute(self):
        self.assertEqual(format_lap_time(92.891), "1:32.891")

    def test_format_lap_time_handles_missing(self):
        self.assertEqual(format_lap_time(None), "N/A")

    @patch("utils.f1_api.requests.get")
    def test_fastest_lap_packet_includes_formatted_lap_time(self, mock_get):
        mock_get.side_effect = [
            _response([SESSION]),
            _response([{"driver_number": 16, "lap_number": 42, "lap_duration": 92.891, "st_speed": 245}]),
            _response([{"full_name": "Charles Leclerc"}]),
        ]
        result = get_fastest_lap_of_race(2024, "Italy", location="Monza")
        self.assertEqual(result["lap_time"], "1:32.891")
        self.assertEqual(result["lap_time_seconds"], 92.891)

    @patch("utils.f1_api.requests.get")
    def test_historical_lap_packet_includes_formatted_lap_time(self, mock_get):
        mock_get.side_effect = [
            _response([SESSION]),
            _response([{"driver_number": 44, "lap_number": 12, "lap_duration": 92.891, "st_speed": 238, "is_pit_out_lap": False}]),
            _response([{"full_name": "Lewis Hamilton"}]),
        ]
        result = get_historical_lap(2024, "Italy", 44, 12, location="Monza")
        self.assertEqual(result["lap_time"], "1:32.891")
        self.assertEqual(result["lap_time_seconds"], 92.891)


if __name__ == "__main__":
    unittest.main()
