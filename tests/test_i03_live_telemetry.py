import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import app
from utils.f1_api import (
    LIVE_DATA_UNAVAILABLE_MESSAGE,
    get_driver_telemetry,
    session_is_live,
)


def _response(payload, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload
    return mock


PAST_SESSION = {
    "session_key": 9565,
    "location": "Silverstone",
    "date_start": "2024-07-07T14:00:00+00:00",
    "date_end": "2024-07-07T16:00:00+00:00",
}

LIVE_SESSION = {
    "session_key": 9999,
    "location": "Spa-Francorchamps",
    "date_start": "2026-08-16T09:00:00+00:00",
    "date_end": "2026-08-16T11:00:00+00:00",
}

NOW_DURING_LIVE = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
NOW_OFF_WEEKEND = datetime(2026, 8, 16, 3, 0, tzinfo=timezone.utc)


class TestI03LiveTelemetry(unittest.TestCase):
    def test_session_is_live_inside_openf1_window(self):
        self.assertTrue(session_is_live(LIVE_SESSION, now=NOW_DURING_LIVE))

    def test_session_is_not_live_for_archive_session(self):
        self.assertFalse(session_is_live(PAST_SESSION, now=NOW_OFF_WEEKEND))

    def test_off_weekend_returns_simple_error_and_does_not_hit_archive(self):
        requested_urls = []

        def fake_get(url, *args, **kwargs):
            requested_urls.append(url)
            if "/sessions" in url:
                return _response([PAST_SESSION])
            raise AssertionError(f"Unexpected request: {url}")

        with patch("utils.f1_api.requests.get", side_effect=fake_get):
            result = get_driver_telemetry(1, now=NOW_OFF_WEEKEND)

        self.assertEqual(result, LIVE_DATA_UNAVAILABLE_MESSAGE)
        self.assertTrue(any("session_key=latest" in url for url in requested_urls))
        self.assertFalse(any("Silverstone" in url for url in requested_urls))
        self.assertFalse(any("9565" in url for url in requested_urls))
        self.assertFalse(any("/car_data" in url for url in requested_urls))

    def test_live_session_fetches_openf1_car_data_with_latest_key(self):
        requested_urls = []

        def fake_get(url, *args, **kwargs):
            requested_urls.append(url)
            if "/sessions" in url:
                return _response([LIVE_SESSION])
            if "/car_data" in url:
                return _response([{"speed": 312, "rpm": 11000, "gear": 7, "drs": 0, "date": "2026-08-16T10:00:01+00:00"}])
            raise AssertionError(f"Unexpected request: {url}")

        with patch("utils.f1_api.requests.get", side_effect=fake_get):
            result = get_driver_telemetry(1, now=NOW_DURING_LIVE)

        self.assertEqual(result["speed"], 312)
        self.assertEqual(result["driver_number"], 1)
        self.assertTrue(any("car_data" in url and "session_key=latest" in url for url in requested_urls))
        self.assertFalse(any("Silverstone" in url for url in requested_urls))
        self.assertFalse(any("9565" in url for url in requested_urls))

    def test_live_session_with_empty_or_forbidden_car_data_returns_error(self):
        def fake_get(url, *args, **kwargs):
            if "/sessions" in url:
                return _response([LIVE_SESSION])
            return _response([], status=403)

        with patch("utils.f1_api.requests.get", side_effect=fake_get):
            result = get_driver_telemetry(44, now=NOW_DURING_LIVE)

        self.assertEqual(result, LIVE_DATA_UNAVAILABLE_MESSAGE)

    def test_app_surfaces_live_error_instead_of_archive_context(self):
        params = {
            "query_type": "live_telemetry",
            "driver_number": 1,
            "year": 2026,
            "country": None,
            "lap_number": None,
        }
        with patch.object(app, "get_driver_telemetry", return_value=LIVE_DATA_UNAVAILABLE_MESSAGE):
            result = app.resolve_quantitative_query(params)

        self.assertEqual(result["kind"], "error")
        self.assertEqual(result["message"], LIVE_DATA_UNAVAILABLE_MESSAGE)


if __name__ == "__main__":
    unittest.main()
