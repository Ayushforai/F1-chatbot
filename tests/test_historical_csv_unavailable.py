import unittest
from unittest.mock import patch

import app
from utils.historical_db import (
    CSV_UNAVAILABLE_MESSAGE,
    csv_available,
    get_driver_teams,
    get_grand_prix_by_country,
    get_historical_driver_info,
    get_lap_time_delta,
    get_race_results,
)


class TestHistoricalCsvAvailability(unittest.TestCase):
    def test_csv_available_when_data_loaded(self):
        self.assertTrue(csv_available())

    @patch("utils.historical_db.races_df", None)
    @patch("utils.historical_db.circuits_df", None)
    @patch("utils.historical_db.drivers_df", None)
    @patch("utils.historical_db.constructors_df", None)
    @patch("utils.historical_db.results_df", None)
    @patch("utils.historical_db.status_df", None)
    @patch("utils.historical_db.lap_times_df", None)
    def test_public_functions_return_message_not_name_error(self):
        self.assertFalse(csv_available())
        for result in (
            get_race_results(2021, "Monaco"),
            get_driver_teams(2012, "Hamilton"),
            get_historical_driver_info(2019, "Hamilton", "Monaco"),
            get_grand_prix_by_country("India"),
            get_lap_time_delta(2017, "Azerbaijan", "Bottas", "Stroll", 32),
        ):
            self.assertIsInstance(result, str)
            self.assertIn("setup_historical_data", result.lower())

    def test_race_results_response_shows_setup_message(self):
        with patch("app.csv_available", return_value=False):
            answer = app._format_race_results_response("results of monaco gp 2021?", [], year=2021)
        self.assertEqual(answer, CSV_UNAVAILABLE_MESSAGE)

    def test_driver_team_handler_shows_setup_message(self):
        history: list[dict] = []
        with patch("app.csv_available", return_value=False):
            handled = app._handle_driver_team_query(
                history,
                "Which team did Hamilton drive for in 2012?",
            )
        self.assertTrue(handled)
        self.assertIn(CSV_UNAVAILABLE_MESSAGE, history[-1]["answer"])


if __name__ == "__main__":
    unittest.main()
