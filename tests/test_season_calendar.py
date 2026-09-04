import unittest
from unittest.mock import patch

from utils.season_calendar import csv_season_calendar, get_season_calendar, list_calendar_years


class SeasonCalendarTests(unittest.TestCase):
    def test_years_include_historical_and_current(self):
        years = list_calendar_years()
        self.assertIn(2021, years)
        self.assertIn(1950, years)
        self.assertGreaterEqual(years[0], years[-1])

    def test_csv_calendar_2021_includes_monaco(self):
        races = csv_season_calendar(2021)
        self.assertGreaterEqual(len(races), 20)
        self.assertEqual(races[0]["round"], 1)
        names = " ".join(race["name"] for race in races)
        self.assertIn("Monaco", names)
        self.assertTrue(races[0]["date"].startswith("2021"))
        self.assertTrue(races[0]["weekend_start"])
        self.assertTrue(races[0]["country"])

    def test_get_season_calendar_prefers_csv(self):
        payload = get_season_calendar(2021)
        self.assertEqual(payload["source"], "csv")
        self.assertEqual(payload["year"], 2021)
        self.assertTrue(payload["races"])

    def test_openf1_calendar_uses_race_day_not_meeting_start(self):
        from utils.f1_api import fetch_year_meetings

        meetings = [
            {
                "meeting_key": 1293,
                "meeting_name": "Italian Grand Prix",
                "date_start": "2026-09-04T10:30:00+00:00",
                "country_name": "Italy",
                "location": "Monza",
                "circuit_short_name": "Monza",
            }
        ]
        race_sessions = [
            {
                "meeting_key": 1293,
                "session_name": "Race",
                "date_start": "2026-09-06T13:00:00+00:00",
            }
        ]

        def fake_get(url, params=None, timeout=None):
            class Response:
                status_code = 200

                def json(self):
                    if url.endswith("/meetings"):
                        return meetings
                    if url.endswith("/sessions"):
                        return race_sessions
                    return []

            return Response()

        with patch("utils.f1_api.requests.get", side_effect=fake_get):
            races = fetch_year_meetings(2026)

        self.assertEqual(races[0]["weekend_start"], "2026-09-04")
        self.assertEqual(races[0]["date"], "2026-09-06")
        self.assertEqual(races[0]["weekend_end"], "2026-09-06")
