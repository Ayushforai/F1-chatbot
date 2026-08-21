import re
import unittest
from unittest.mock import patch

import app
from historical_processor import build_historical_documents
from utils.historical_db import get_race_results


class TestI04FullClassification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = build_historical_documents()
        cls.british_2008 = next(
            (
                d
                for d in cls.docs
                if d.metadata.get("year") == 2008 and "British" in str(d.metadata.get("race", ""))
            ),
            None,
        )

    def test_race_document_is_not_capped_at_top_10(self):
        self.assertIsNotNone(self.british_2008)
        text = self.british_2008.page_content
        position_lines = re.findall(r"^P\S+:", text, flags=re.M)
        self.assertGreater(
            len(position_lines),
            10,
            "2008 British GP document should include the full grid, not only the top 10",
        )
        self.assertIn("full race classification", text)

    def test_race_document_includes_fastest_laps(self):
        text = self.british_2008.page_content
        self.assertIn("Overall fastest lap", text)
        self.assertIn("fastest lap", text.lower())
        self.assertRegex(text, r"Overall fastest lap: Kimi")

    def test_csv_lookup_returns_full_classification_and_overall_fastest_lap(self):
        data = get_race_results(2008, "Great Britain")
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data["Classification"]), 10)
        self.assertIn("Overall Fastest Lap", data)
        self.assertEqual(data["Overall Fastest Lap"]["Driver"], "Kimi Räikkönen")
        self.assertEqual(data["Overall Fastest Lap"]["Time"], "1:32.150")
        outside_points = [row for row in data["Classification"] if str(row["Position"]) not in {str(i) for i in range(1, 11)}]
        self.assertTrue(outside_points)

    def test_complete_results_query_prefers_csv_over_rag(self):
        packet = {
            "Year": 2008,
            "Grand Prix": "British Grand Prix",
            "Classification": [{"Position": str(i)} for i in range(1, 21)],
            "Overall Fastest Lap": {"Driver": "Kimi Räikkönen", "Time": "1:32.150"},
        }
        with (
            patch("app.extract_telemetry_params", return_value={"year": 2008, "country": "Great Britain", "driver_name": ""}),
            patch("app.get_historical_driver_info", return_value=packet) as csv_fn,
            patch("app.vector_search") as rag,
        ):
            ctx = app._historical_context("complete race results of the 2008 British Grand Prix", [])

        csv_fn.assert_called()
        rag.assert_not_called()
        self.assertIn("British Grand Prix", ctx)
        self.assertIn("The results for the 2008 British Grand Prix are as follows:", ctx)

    def test_plain_results_query_uses_csv(self):
        self.assertTrue(app._wants_full_classification_or_pace("results of brazilian gp 2021?"))
        packet = {
            "Year": 2021,
            "Grand Prix": "São Paulo Grand Prix",
            "Classification": [{"Position": str(i)} for i in range(1, 21)],
        }
        with (
            patch("app.extract_telemetry_params", return_value={"year": 2026, "country": "Brazil", "driver_name": ""}),
            patch("app.get_historical_driver_info", return_value=packet) as csv_fn,
            patch("app.vector_search") as rag,
        ):
            ctx = app._historical_context("results of brazilian gp 2021?", [])
        csv_fn.assert_called_once()
        self.assertEqual(csv_fn.call_args.args[0], 2021)
        rag.assert_not_called()
        self.assertIn("São Paulo", ctx)
        self.assertIn("The results for the 2021", ctx)

    def test_csv_finds_2021_sao_paulo_under_brazil(self):
        data = get_race_results(2021, "Brazil")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["Grand Prix"], "São Paulo Grand Prix")
        self.assertGreater(len(data["Classification"]), 10)

    def test_formatted_2021_brazil_includes_both_dnfs(self):
        from utils.historical_db import format_race_classification

        data = get_race_results(2021, "Brazil")
        text = format_race_classification(data)
        self.assertIn("The results for the 2021 São Paulo Grand Prix are as follows:", text)
        self.assertIn("Lewis Hamilton", text)
        self.assertIn("1. Lewis Hamilton", text)
        self.assertIn("Classified finishers (18):", text)
        self.assertIn("Did not finish (2):", text)
        self.assertIn("Daniel Ricciardo", text)
        self.assertIn("Cause: Power loss", text)
        self.assertIn("Lance Stroll", text)
        self.assertIn("Cause: Collision damage", text)
        self.assertIn("Sergio Pérez", text)
        classified_lines = [ln for ln in text.splitlines() if re.match(r"^\d+\.", ln)]
        self.assertEqual(len(classified_lines), 18)
        self.assertTrue(app._is_race_results_query("results of brazilian gp 2021?"))
        self.assertTrue(app._is_race_results_query("results of monaco gp?"))

    def test_formatted_2019_germany_lists_all_classified_and_retirements(self):
        from utils.historical_db import format_race_classification
        from utils.venues import resolve_venue

        self.assertEqual(resolve_venue(query="results of german gp 2019?")["kind"], "ok")
        data = get_race_results(2019, "Germany")
        text = format_race_classification(data)
        classified_lines = [ln for ln in text.splitlines() if re.match(r"^\d+\.", ln)]
        self.assertEqual(len(classified_lines), 14)
        self.assertIn("Classified finishers (14):", text)
        self.assertIn("Did not finish (6):", text)
        self.assertIn("Cause: Accident", text)
        self.assertIn("Cause: Spun off", text)

    def test_formatted_2019_austria_lists_all_twenty_finishers(self):
        from utils.historical_db import format_race_classification

        data = get_race_results(2019, "Austria")
        text = format_race_classification(data)
        self.assertIn("Classified finishers (20):", text)
        self.assertIn("Did not finish: none recorded for this race.", text)
        classified_lines = [ln for ln in text.splitlines() if re.match(r"^\d+\.", ln)]
        self.assertEqual(len(classified_lines), 20)

    def test_german_gp_2019_prefers_csv_over_rag(self):
        with (
            patch("app.extract_telemetry_params", return_value={"year": 2026, "country": None, "driver_name": ""}),
            patch("app.vector_search") as rag,
        ):
            ctx = app._historical_context("results of german gp 2019?", [])

        rag.assert_not_called()
        self.assertIn("German Grand Prix", ctx)
        self.assertIn("Classified finishers (14):", ctx)
        self.assertIn("Did not finish (6):", ctx)
        classified_lines = [ln for ln in ctx.splitlines() if re.match(r"^\d+\.", ln)]
        self.assertEqual(len(classified_lines), 14)

    def test_year_in_query_overrides_extractor_default(self):
        self.assertEqual(app._year_from_query("results of brazilian gp 2021?", 2026), 2021)

    def test_race_results_without_year_do_not_use_csv_silently(self):
        self.assertIsNone(app._csv_historical_record("results of monaco gp?", []))

    def test_race_results_with_year_use_csv(self):
        ctx = app._csv_historical_record("results of monaco gp 2021?", [], year=2021)
        self.assertIsNotNone(ctx)
        self.assertIn("Monaco Grand Prix", ctx)


if __name__ == "__main__":
    unittest.main()
