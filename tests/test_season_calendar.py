import unittest

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
