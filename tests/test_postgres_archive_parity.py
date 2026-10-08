"""Golden archive queries (issue-fix set) on CSV, plus Postgres parity when DATABASE_URL works."""

from __future__ import annotations

import os
import unittest
from decimal import Decimal

from utils.db import database_url, reset_backend_cache
from utils.historical_db import (
    get_driver_standing,
    get_driver_teams,
    get_qualifying_results,
    get_race_results,
    get_sprint_results,
)


def _jsonish(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonish(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonish(item) for item in value]
    return value


def _postgres_ready() -> bool:
    if not database_url():
        return False
    try:
        from utils.historical_pg import archive_available

        return archive_available()
    except Exception:
        return False


# Queries used across I04/I05/I06/I08, standings, session offer, and deploy smoke.
GOLDEN_RACE_QUERIES = (
    (2021, "Monaco", None, "Max Verstappen", 18),
    (2008, "Great Britain", None, "Kimi Räikkönen", 10),
    (2021, "Brazil", None, None, 10),
    (2019, "Germany", None, None, 10),
    (2019, "Austria", None, None, 10),
    (2019, "Italy", None, "Charles Leclerc", 10),
    (2024, "Italy", None, None, 0),
)


class TestIssueFixArchiveQueriesCsv(unittest.TestCase):
    """Previous regression queries — always run against the CSV backend."""

    @classmethod
    def setUpClass(cls):
        os.environ["HISTORICAL_BACKEND"] = "csv"
        reset_backend_cache()

    def test_i04_monaco_2021_full_grid_verstappen_wins(self):
        data = get_race_results(2021, "Monaco")
        self.assertIsInstance(data, dict)
        self.assertGreaterEqual(len(data["Classification"]), 18)
        self.assertEqual(data["Classification"][0]["Driver"], "Max Verstappen")
        self.assertEqual(data["Classification"][2]["Driver"], "Lando Norris")

    def test_i04_british_2008_full_grid_and_fastest_lap(self):
        data = get_race_results(2008, "Great Britain")
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data["Classification"]), 10)
        self.assertEqual(data["Overall Fastest Lap"]["Driver"], "Kimi Räikkönen")
        self.assertEqual(data["Overall Fastest Lap"]["Time"], "1:32.150")

    def test_i05_hamilton_2012_mclaren(self):
        result = get_driver_teams(2012, "Hamilton")
        self.assertEqual(result["Teams"][0]["Team"], "McLaren")
        self.assertEqual(result["Teams"][0]["Races"], 20)

    def test_i05_stroll_2018_williams(self):
        result = get_driver_teams(2018, "lance stroll")
        self.assertEqual(result["Teams"][0]["Team"], "Williams")

    def test_i05_alonso_2007_mclaren(self):
        result = get_driver_teams(2007, "Alonso")
        self.assertEqual(result["Teams"][0]["Team"], "McLaren")

    def test_hamilton_2012_standings_p4_190pts(self):
        result = get_driver_standing(2012, "Hamilton")
        self.assertEqual(result["Position"], 4)
        self.assertEqual(float(result["Points"]), 190.0)
        self.assertEqual(result["Wins"], 4)

    def test_i08_italy_2019_single_gp_resolves_monza(self):
        """2019 Italy had only Monza — no Imola — so CSV returns Italian GP, not a clarify prompt."""
        data = get_race_results(2019, "Italy")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["Grand Prix"], "Italian Grand Prix")
        self.assertEqual(data["Classification"][0]["Driver"], "Charles Leclerc")

    def test_i08_italy_2024_without_venue_clarifies(self):
        result = get_race_results(2024, "Italy")
        self.assertIsInstance(result, str)
        self.assertIn("Monza", result)
        self.assertIn("Imola", result)

    def test_monaco_2021_qualifying_leclerc_pole(self):
        data = get_qualifying_results(2021, "Monaco")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["Grid"][0]["Driver"], "Charles Leclerc")

    def test_smoke_query_who_was_third_monaco_2021(self):
        """Deploy smoke: Results of Monaco GP 2021 → third is Lando Norris."""
        data = get_race_results(2021, "Monaco")
        third = data["Classification"][2]
        self.assertEqual(third["Driver"], "Lando Norris")
        self.assertEqual(str(third["Position"]), "3")


@unittest.skipUnless(_postgres_ready(), "PostgreSQL archive not loaded (DATABASE_URL / f1.races)")
class TestPostgresMatchesCsvGoldens(unittest.TestCase):
    def test_race_packets_match_csv(self):
        from utils.historical_pg import get_race_results as pg_results

        os.environ["HISTORICAL_BACKEND"] = "csv"
        reset_backend_cache()
        for year, country, location, winner, min_grid in GOLDEN_RACE_QUERIES:
            with self.subTest(year=year, country=country, location=location):
                csv_data = get_race_results(year, country, location=location)
                pg_data = pg_results(year, country, location=location)
                self.assertEqual(type(csv_data), type(pg_data))
                if isinstance(csv_data, str):
                    self.assertEqual(csv_data, pg_data)
                    continue
                self.assertGreaterEqual(len(csv_data["Classification"]), min_grid)
                if winner:
                    self.assertEqual(csv_data["Classification"][0]["Driver"], winner)
                self.assertEqual(_jsonish(csv_data), _jsonish(pg_data))

    def test_teams_standings_quali_sprint_match_csv(self):
        from utils.historical_pg import (
            get_driver_standing as pg_standing,
            get_driver_teams as pg_teams,
            get_qualifying_results as pg_quali,
            get_sprint_results as pg_sprint,
        )

        os.environ["HISTORICAL_BACKEND"] = "csv"
        reset_backend_cache()
        self.assertEqual(
            _jsonish(get_driver_teams(2012, "Hamilton")),
            _jsonish(pg_teams(2012, "Hamilton")),
        )
        self.assertEqual(
            _jsonish(get_driver_standing(2012, "Hamilton")),
            _jsonish(pg_standing(2012, "Hamilton")),
        )
        self.assertEqual(
            _jsonish(get_qualifying_results(2021, "Monaco")),
            _jsonish(pg_quali(2021, "Monaco")),
        )
        self.assertEqual(
            _jsonish(get_sprint_results(2021, "Brazil")),
            _jsonish(pg_sprint(2021, "Brazil")),
        )


if __name__ == "__main__":
    unittest.main()
